"""SSE streaming endpoint for real-time agent output."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

from fastapi import APIRouter, HTTPException, Request
from starlette.responses import StreamingResponse

from app.streaming.sse import format_sse_done, format_sse_event

router = APIRouter(prefix="/api/tasks", tags=["streaming"])

_POLL_INTERVAL = 0.5


def _storage(request: Request):
    return request.app.state.storage


def _runner(request: Request):
    return request.app.state.runner


async def _event_stream(task_id: str, request: Request) -> AsyncGenerator[str, None]:
    storage = _storage(request)
    runner = _runner(request)
    last_event_id: str | None = None
    while True:
        if await request.is_disconnected():
            break
        events = storage.read_events(task_id, after_id=last_event_id)
        for event in events:
            yield format_sse_event(event.type, event.model_dump())
            last_event_id = event.id
        if not runner.is_running(task_id):
            remaining = storage.read_events(task_id, after_id=last_event_id)
            for event in remaining:
                yield format_sse_event(event.type, event.model_dump())
                last_event_id = event.id
            yield format_sse_done()
            break
        await asyncio.sleep(_POLL_INTERVAL)


@router.get("/{task_id}/stream")
def stream_task(task_id: str, request: Request) -> StreamingResponse:
    storage = _storage(request)
    state = storage.get_task(task_id, include_events=False)
    if state.status == "idle" and not state.messages:
        raise HTTPException(status_code=404, detail="任务不存在")
    return StreamingResponse(
        _event_stream(task_id, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
