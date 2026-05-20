from __future__ import annotations

import logging
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from hmac import compare_digest
from ipaddress import ip_address
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.responses import Response
from starlette.types import Message

from .agent_store import PostgresAgentStore
from .api.artifacts import router as artifacts_router
from .api.files import router as files_router
from .api.models import router as models_router
from .api.skills import router as skills_router
from .api.streaming import router as streaming_router
from .api.tasks import router as tasks_router
from .config import Settings, enforce_single_process_runtime, load_settings
from .conversation_context import ConversationContextBuilder
from .memory import AgentMemoryService, MemoryServiceError
from .runner.core import TaskRunner
from .storage import PostgresTaskStorage
from .task_titles import generate_task_title

logger = logging.getLogger(__name__)


class RequestBodyTooLarge(Exception):
    """Raised when a streaming request body exceeds the configured limit."""


def create_app(
    settings: Settings | None = None,
    *,
    storage: Any | None = None,
    memory_service: AgentMemoryService | None = None,
    title_generator: Callable[[str, str, Settings], Awaitable[str]] | None = None,
) -> FastAPI:
    resolved = settings or load_settings()
    enforce_single_process_runtime()

    startup_errors: list[str] = []
    external_services_required = storage is None
    if storage is None:
        if not resolved.database_url:
            startup_errors.append("MYAGENT_DATABASE_URL 未配置")
        else:
            storage = PostgresTaskStorage(resolved.task_root, resolved.database_url)

    if external_services_required and memory_service is None:
        try:
            memory_service = AgentMemoryService(resolved, storage)
        except MemoryServiceError as exc:
            startup_errors.append(str(exc))

    context_builder = ConversationContextBuilder(resolved, storage) if storage is not None else None
    agent_store = PostgresAgentStore(storage) if storage is not None else None
    runner = TaskRunner(
        resolved,
        storage,
        memory_service,
        context_builder=context_builder,
        agent_store=agent_store,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
        if startup_errors:
            raise RuntimeError("；".join(startup_errors))
        assert storage is not None
        if hasattr(storage, "initialize"):
            storage.initialize()
        if memory_service is not None:
            memory_service.startup_check()
        interrupted = storage.interrupt_running_tasks("后端启动或重载时中断了任务。")
        if interrupted:
            logger.info("Startup interrupted %d running task(s): %s", len(interrupted), interrupted)
        yield

    app = FastAPI(title="MyAgent Backend", version="0.2.0", lifespan=lifespan)
    app.state.settings = resolved
    app.state.storage = storage
    app.state.runner = runner
    app.state.title_generator = title_generator or generate_task_title

    app.include_router(tasks_router)
    app.include_router(files_router)
    app.include_router(artifacts_router)
    app.include_router(streaming_router)
    app.include_router(models_router)
    app.include_router(skills_router)

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
        if request.url.path.startswith("/api/") and request.method != "OPTIONS":
            access_response = authorize_task_request(request, resolved)
            if access_response is not None:
                return access_response
        if request.method in {"POST", "PUT", "PATCH"} and is_multipart_request(request):
            multipart_limit_response = enforce_content_length_limit(
                request, resolved.max_upload_request_bytes, "上传请求"
            )
            if multipart_limit_response is not None:
                return multipart_limit_response
            install_receive_body_limit(request, resolved.max_upload_request_bytes, "上传请求")
        if request.method in {"POST", "PUT", "PATCH"} and is_json_request(request):
            json_limit_response = await enforce_json_body_limit(
                request, resolved.max_json_request_bytes
            )
            if json_limit_response is not None:
                return json_limit_response
        try:
            return await call_next(request)
        except RequestBodyTooLarge as exc:
            return JSONResponse(status_code=413, content={"detail": str(exc)})

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved.cors_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-MyAgent-Token", "X-Agent-Chat-Token"],
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


def is_json_request(request: Request) -> bool:
    return "application/json" in request.headers.get("content-type", "").lower()


def is_multipart_request(request: Request) -> bool:
    return "multipart/form-data" in request.headers.get("content-type", "").lower()


def enforce_content_length_limit(
    request: Request, max_bytes: int, label: str
) -> JSONResponse | None:
    raw_length = request.headers.get("content-length")
    if raw_length is None:
        return None
    try:
        content_length = int(raw_length)
    except ValueError:
        return JSONResponse(status_code=400, content={"detail": "Content-Length 请求头无效"})
    if content_length > max_bytes:
        return JSONResponse(
            status_code=413,
            content={"detail": f"{label}超过 {max_bytes} 字节限制"},
        )
    return None


def install_receive_body_limit(request: Request, max_bytes: int, label: str) -> None:
    """Wrap ASGI receive so multipart bodies are limited before UploadFile parsing."""
    original_receive = request._receive  # noqa: SLF001
    bytes_seen = 0

    async def limited_receive() -> Message:
        nonlocal bytes_seen
        message = await original_receive()
        if message.get("type") == "http.request":
            body = message.get("body", b"")
            bytes_seen += len(body)
            if bytes_seen > max_bytes:
                raise RequestBodyTooLarge(f"{label}超过 {max_bytes} 字节限制")
        return message

    request._receive = limited_receive  # noqa: SLF001


async def enforce_json_body_limit(request: Request, max_bytes: int) -> JSONResponse | None:
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > max_bytes:
            return JSONResponse(
                status_code=413,
                content={"detail": f"JSON 请求超过 {max_bytes} 字节限制"},
            )
    request._body = bytes(body)  # noqa: SLF001
    return None


def authorize_task_request(request: Request, settings: Settings) -> JSONResponse | None:
    if settings.access_token:
        supplied_token = (
            request.headers.get("x-myagent-token")
            or request.headers.get("x-agent-chat-token")
            or request.query_params.get("token")
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
