"""Server-Sent Events formatter and endpoint helpers."""

from __future__ import annotations

import json
from typing import Any


def format_sse_event(event_type: str, data: dict[str, Any]) -> str:
    """Format a single SSE frame with ``event`` and ``data`` fields."""
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event_type}\ndata: {payload}\n\n"


def format_sse_message(chunk: str) -> str:
    """Format a text chunk as an SSE ``message`` event."""
    payload = json.dumps({"content": chunk}, ensure_ascii=False)
    return f"event: message\ndata: {payload}\n\n"


def format_sse_done() -> str:
    """Format the SSE completion signal."""
    return "event: done\ndata: {}\n\n"
