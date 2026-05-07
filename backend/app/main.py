from __future__ import annotations

from collections.abc import Awaitable, Callable
from hmac import compare_digest
from ipaddress import ip_address
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette.responses import Response

from .model_provider import ProviderRouter
from .runner import TaskRunner
from .schemas import (
    EventRecord,
    MessageRequest,
    ModelOption,
    TaskCreateRequest,
    TaskState,
    TaskSummary,
)
from .settings import MODEL_REGISTRY, Settings, enforce_single_process_runtime, load_settings
from .storage import TaskStorage, UploadConflictError, UploadLimitError


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or load_settings()
    enforce_single_process_runtime()
    storage = TaskStorage(resolved_settings.task_root)
    storage.interrupt_running_tasks("后端启动或重载时中断了任务。")
    runner = TaskRunner(storage, ProviderRouter(resolved_settings), resolved_settings)

    app = FastAPI(title="MyAgent Backend", version="0.1.0")
    app.state.settings = resolved_settings
    app.state.storage = storage
    app.state.runner = runner

    @app.exception_handler(RequestValidationError)
    async def request_validation_exception_handler(
        _request: Request, _exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"detail": "请求参数校验失败，请检查输入内容。"},
        )

    @app.middleware("http")
    async def enforce_request_limits_and_task_access(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.url.path.startswith("/api/tasks") and request.method != "OPTIONS":
            access_response = authorize_task_request(request, resolved_settings)
            if access_response is not None:
                return access_response

        if request.method == "POST" and request.url.path.endswith("/files"):
            content_length = request.headers.get("content-length")
            if (
                content_length is not None
                and content_length.isdigit()
                and int(content_length) > resolved_settings.max_upload_request_bytes
            ):
                return JSONResponse(
                    status_code=413,
                    content={
                        "detail": (
                            "上传请求超过 "
                            f"{resolved_settings.max_upload_request_bytes} 字节总量限制"
                        )
                    },
                )
        if request.method in {"POST", "PUT", "PATCH"} and is_json_request(request):
            json_limit_response = await enforce_json_body_limit(
                request, resolved_settings.max_json_request_bytes
            )
            if json_limit_response is not None:
                return json_limit_response
        return await call_next(request)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved_settings.cors_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-MyAgent-Token", "X-Agent-Chat-Token"],
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/models", response_model=list[ModelOption])
    def list_models() -> list[dict[str, object]]:
        return MODEL_REGISTRY

    @app.post("/api/tasks", response_model=TaskState)
    def create_task(request: TaskCreateRequest) -> TaskState:
        validate_model(request.model)
        if request.message is not None:
            raise HTTPException(
                status_code=400,
                detail="请先创建不含初始消息的任务，再通过 /messages 发送消息。",
            )
        return storage.create_task(None, request.model)

    @app.get("/api/tasks", response_model=list[TaskSummary])
    def list_tasks() -> list[TaskSummary]:
        return storage.list_task_summaries()

    @app.get("/api/tasks/{task_id}", response_model=TaskState)
    def get_task(task_id: str, include_events: bool = Query(True)) -> TaskState:
        return require_task(storage, task_id, include_events=include_events)

    @app.get("/api/tasks/{task_id}/events", response_model=list[EventRecord])
    def get_task_events(task_id: str, after_id: str | None = None) -> list[EventRecord]:
        require_task(storage, task_id, include_events=False)
        return storage.read_events(task_id, after_id=after_id)

    @app.post("/api/tasks/{task_id}/files", response_model=TaskState)
    def upload_files(task_id: str, files: list[UploadFile] = File(...)) -> TaskState:
        state = require_task(storage, task_id)
        if state.status == "running" and not runner.is_running(task_id):
            storage.mark_interrupted_if_running(
                task_id, "任务已中断：当前没有运行器接管该任务。"
            )
            state = storage.get_task(task_id)
        if state.status == "running" or runner.is_running(task_id):
            raise HTTPException(
                status_code=409,
                detail="任务运行中不能上传文件",
            )
        try:
            storage.save_uploads(
                task_id,
                files,
                max_files=resolved_settings.max_upload_files,
                max_file_bytes=resolved_settings.max_upload_file_bytes,
                max_request_bytes=resolved_settings.max_upload_request_bytes,
            )
        except UploadLimitError as exc:
            raise HTTPException(status_code=413, detail=str(exc)) from exc
        except UploadConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return storage.get_task(task_id)

    @app.post("/api/tasks/{task_id}/messages", response_model=TaskState)
    def send_message(task_id: str, request: MessageRequest) -> TaskState:
        require_task(storage, task_id)
        validate_model(request.model)
        try:
            runner.start(
                task_id,
                request.message,
                request.model,
                mode=request.mode,
                input_scope=request.input_scope,
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return storage.get_task(task_id)

    @app.post("/api/tasks/{task_id}/cancel", response_model=TaskState)
    def cancel_task(task_id: str) -> TaskState:
        require_task(storage, task_id)
        runner.cancel(task_id)
        return storage.get_task(task_id)

    @app.get("/api/tasks/{task_id}/runs/{run_id}/artifacts/{artifact_name}")
    def get_run_artifact(task_id: str, run_id: str, artifact_name: str) -> FileResponse:
        require_task(storage, task_id)
        try:
            path = storage.resolve_run_artifact(task_id, run_id, artifact_name)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="未找到产物") from None
        if not path.exists():
            raise HTTPException(status_code=404, detail="未找到产物")
        media_type = media_type_for(path)
        return FileResponse(path, media_type=media_type, filename=path.name)

    @app.get("/api/tasks/{task_id}/artifacts/{artifact_name}")
    def get_artifact(task_id: str, artifact_name: str) -> FileResponse:
        require_task(storage, task_id)
        try:
            path = storage.resolve_artifact(task_id, artifact_name)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="未找到产物") from None
        if not path.exists():
            raise HTTPException(status_code=404, detail="未找到产物")
        media_type = media_type_for(path)
        return FileResponse(path, media_type=media_type, filename=path.name)

    return app


def validate_model(model: str) -> None:
    if model not in {item["id"] for item in MODEL_REGISTRY}:
        raise HTTPException(status_code=400, detail=f"不支持的模型：{model}")


def require_task(storage: TaskStorage, task_id: str, *, include_events: bool = True) -> TaskState:
    try:
        return storage.get_task(task_id, include_events=include_events)
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=404, detail="未找到任务") from None


def media_type_for(path: Path) -> str:
    if path.suffix.lower() == ".html":
        return "text/html"
    if path.suffix.lower() == ".md":
        return "text/markdown"
    if path.suffix.lower() == ".json":
        return "application/json"
    return "text/plain"


def is_json_request(request: Request) -> bool:
    return "application/json" in request.headers.get("content-type", "").lower()


async def enforce_json_body_limit(request: Request, max_bytes: int) -> JSONResponse | None:
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > max_bytes:
            return JSONResponse(
                status_code=413,
                content={"detail": f"JSON 请求超过 {max_bytes} 字节限制"},
            )
    request._body = bytes(body)  # noqa: SLF001 - Starlette reuses this for downstream parsing.
    return None


def authorize_task_request(request: Request, settings: Settings) -> JSONResponse | None:
    if settings.access_token:
        supplied_token = (
            request.headers.get("x-myagent-token")
            or request.headers.get("x-agent-chat-token")
            or bearer_token(request)
        )
        if supplied_token and compare_digest(supplied_token, settings.access_token):
            return None
        return JSONResponse(status_code=401, content={"detail": "访问令牌无效或缺失。"})
    if is_local_client(request):
        return None
    return JSONResponse(
        status_code=403,
        content={
            "detail": "任务 API 默认只允许本机访问；如需非本机访问，请设置 MYAGENT_ACCESS_TOKEN"
        },
    )


def bearer_token(request: Request) -> str | None:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() == "bearer" and token:
        return token
    return None


def is_local_client(request: Request) -> bool:
    host = request.client.host if request.client else ""
    if host in {"testclient", "localhost"}:
        return True
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False


app = create_app()
