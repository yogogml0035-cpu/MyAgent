"""SSE streaming endpoint for real-time agent output."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator

from fastapi import APIRouter, HTTPException, Request
from starlette.responses import StreamingResponse

from app.streaming.sse import format_sse_done

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tasks", tags=["streaming"])

_POLL_INTERVAL = 0.5


def _storage(request: Request):
    return request.app.state.storage


def _runner(request: Request):
    return request.app.state.runner


def _format_event_record(record) -> str:
    """Serialize a full EventRecord as an SSE data event.

    The frontend ``normalizeLog`` expects the complete EventRecord shape
    (``id``, ``type``, ``message``, ``payload``, ``run_id``, ``level``, etc.)
    rather than the flattened ``{type, **payload}`` format that was used
    previously.  Sending the full record ensures that ``normalizeLiveMetadata``,
    ``normalizeAssistantAnswerStream`` and other extractors can read nested
    fields correctly.
    """
    payload = json.dumps(record.model_dump(), ensure_ascii=False)
    return f"data: {payload}\n\n"


async def _event_stream(task_id: str, request: Request) -> AsyncGenerator[str, None]:
    storage = _storage(request)
    runner = _runner(request)
    last_event_id = None
    try:
        while True:
            if request and await request.is_disconnected():
                break
            events = storage.read_events(task_id, after_id=last_event_id)
            for event in events:
                last_event_id = event.id
                yield _format_event_record(event)
            if not runner.is_running(task_id):
                # Drain any events written after the runner finished
                # but before we observed the status change.
                await asyncio.sleep(0.15)
                remaining = storage.read_events(task_id, after_id=last_event_id)
                for event in remaining:
                    last_event_id = event.id
                    yield _format_event_record(event)
                yield format_sse_done()
                break
            await asyncio.sleep(_POLL_INTERVAL)
    except Exception as exc:
        logger.warning("SSE stream error for task %s: %s", task_id, exc)
        error_payload = json.dumps(
            {"type": "error", "detail": "流传输异常，请刷新页面。"},
            ensure_ascii=False,
        )
        yield f"data: {error_payload}\n\n"
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
