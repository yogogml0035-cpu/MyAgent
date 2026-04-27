from __future__ import annotations

from collections.abc import Awaitable, Callable
from hmac import compare_digest
from ipaddress import ip_address
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette.responses import Response

from .model_provider import ProviderRouter
from .runner import TaskRunner
from .schemas import EventRecord, MessageRequest, ModelOption, TaskCreateRequest, TaskState
from .settings import MODEL_REGISTRY, Settings, enforce_single_process_runtime, load_settings
from .storage import TaskStorage, UploadConflictError, UploadLimitError


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or load_settings()
    enforce_single_process_runtime()
    storage = TaskStorage(resolved_settings.task_root)
    storage.interrupt_running_tasks("Task was interrupted by backend startup or reload.")
    runner = TaskRunner(storage, ProviderRouter(resolved_settings), resolved_settings)

    app = FastAPI(title="MyAgent Backend", version="0.1.0")
    app.state.settings = resolved_settings
    app.state.storage = storage
    app.state.runner = runner

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
                            "Upload request exceeds the "
                            f"{resolved_settings.max_upload_request_bytes} byte limit"
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
        allow_methods=["*"],
        allow_headers=["*"],
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
        return storage.create_task(request.message, request.model)

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
                task_id, "Task was interrupted because no active runner owns it."
            )
            state = storage.get_task(task_id)
        if state.status == "running" or runner.is_running(task_id):
            raise HTTPException(
                status_code=409,
                detail="Cannot upload files while the task is running",
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
            runner.start(task_id, request.message, request.model)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return storage.get_task(task_id)

    @app.post("/api/tasks/{task_id}/cancel", response_model=TaskState)
    def cancel_task(task_id: str) -> TaskState:
        require_task(storage, task_id)
        runner.cancel(task_id)
        return storage.get_task(task_id)

    @app.get("/api/tasks/{task_id}/artifacts/{artifact_name}")
    def get_artifact(task_id: str, artifact_name: str) -> FileResponse:
        require_task(storage, task_id)
        try:
            path = storage.resolve_artifact(task_id, artifact_name)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not path.exists():
            raise HTTPException(status_code=404, detail="Artifact not found")
        media_type = media_type_for(path)
        return FileResponse(path, media_type=media_type, filename=path.name)

    return app


def validate_model(model: str) -> None:
    if model not in {item["id"] for item in MODEL_REGISTRY}:
        raise HTTPException(status_code=400, detail=f"Unsupported model: {model}")


def require_task(storage: TaskStorage, task_id: str, *, include_events: bool = True) -> TaskState:
    try:
        return storage.get_task(task_id, include_events=include_events)
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=404, detail="Task not found") from None


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
                content={"detail": f"JSON request exceeds the {max_bytes} byte limit"},
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
        return JSONResponse(status_code=401, content={"detail": "Invalid or missing access token"})
    if is_local_client(request):
        return None
    return JSONResponse(
        status_code=403,
        content={
            "detail": "Task APIs are restricted to localhost unless MYAGENT_ACCESS_TOKEN is set"
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
