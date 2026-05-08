"""SSE streaming endpoint for real-time agent output."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator

from fastapi import APIRouter, HTTPException, Request
from starlette.responses import StreamingResponse

from app.streaming.sse import format_sse_done, format_sse_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tasks", tags=["streaming"])

_POLL_INTERVAL = 0.5


def _storage(request: Request):
    return request.app.state.storage


def _runner(request: Request):
    return request.app.state.runner


async def _event_stream(task_id: str, request: Request) -> AsyncGenerator[str, None]:
    storage = _storage(request)
    runner = _runner(request)
    last_event_id = ""
    try:
        while True:
            if request and await request.is_disconnected():
                break
            if not runner.is_running(task_id):
                await asyncio.sleep(0.3)
                yield format_sse_done()
                break
            events = storage.read_events(task_id, after_id=last_event_id)
            for event in events:
                last_event_id = event.id
                yield format_sse_event(event.type, event.payload or {})
            await asyncio.sleep(_POLL_INTERVAL)
    except Exception as exc:
        logger.warning("SSE stream error for task %s: %s", task_id, exc)
        yield format_sse_event("error", {"detail": "流传输异常，请刷新页面。"})
        yield format_sse_done()


@router.get("/{task_id}/stream")
def stream_task(task_id: str, request: Request) -> StreamingResponse:
    storage = _storage(request)
    try:
        storage.get_task(task_id, include_events=False)
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=404, detail="任务不存在") from None
    return StreamingResponse(
        _event_stream(task_id, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
