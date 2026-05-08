from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from hmac import compare_digest
from ipaddress import ip_address

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.responses import Response

from .api.files import router as files_router
from .api.models import router as models_router
from .api.streaming import router as streaming_router
from .api.tasks import router as tasks_router
from .config import Settings, enforce_single_process_runtime, load_settings
from .runner.core import TaskRunner
from .storage import TaskStorage

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or load_settings()
    enforce_single_process_runtime()

    app = FastAPI(title="MyAgent Backend", version="0.2.0")
    app.state.settings = resolved

    storage = TaskStorage(resolved.task_root)
    runner = TaskRunner(resolved)
    app.state.storage = storage
    app.state.runner = runner

    @app.on_event("startup")
    def on_startup() -> None:
        interrupted = storage.interrupt_running_tasks("后端启动或重载时中断了任务。")
        if interrupted:
            logger.info("Startup interrupted %d running task(s): %s", len(interrupted), interrupted)

    app.include_router(tasks_router)
    app.include_router(files_router)
    app.include_router(streaming_router)
    app.include_router(models_router)

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
        if request.method in {"POST", "PUT", "PATCH"} and is_json_request(request):
            json_limit_response = await enforce_json_body_limit(
                request, resolved.max_json_request_bytes
            )
            if json_limit_response is not None:
                return json_limit_response
        return await call_next(request)

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
