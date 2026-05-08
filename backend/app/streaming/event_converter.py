"""Convert LangGraph stream events to MyAgent event records."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from app.schemas import EventRecord

# Mapping from adapter event type to EventRecord type string.
_TYPE_MAP: dict[str, str] = {
    "message_chunk": "agent_message",
    "tool_call": "tool_call",
    "tool_result": "tool_result",
    "state_update": "status_update",
}

# Default level per event type.
_LEVEL_MAP: dict[str, Literal["info", "success", "warning", "error"]] = {
    "agent_message": "info",
    "tool_call": "info",
    "tool_result": "info",
    "status_update": "info",
}


def convert_stream_event(
    event: dict[str, Any],
    task_id: str,
    run_id: str,
    *,
    seq: int | None = None,
) -> EventRecord | None:
    """Convert a normalized stream event dict to an :class:`EventRecord`.

    Returns ``None`` for unrecognized event types.
    """
    event_type: str | None = event.get("type")
    data = event.get("data", {})

    record_type = _TYPE_MAP.get(event_type) if event_type is not None else None
    if record_type is None:
        return None

    message = _build_message(record_type, data)
    level = _LEVEL_MAP.get(record_type, "info")

    return EventRecord(
        id=str(uuid.uuid4()),
        session_id=task_id,
        seq=seq,
        type=record_type,
        message=message,
        created_at=datetime.now(tz=timezone.utc).isoformat(),
        payload=data,
        run_id=run_id,
        level=level,
    )


def _build_message(record_type: str, data: dict[str, Any]) -> str:
    if record_type == "agent_message":
        return data.get("content", "")
    if record_type == "tool_call":
        name = data.get("name", "unknown")
        return f"Calling tool: {name}"
    if record_type == "tool_result":
        name = data.get("name", "unknown")
        status = data.get("status", "ok")
        return f"Tool result ({name}): {status}"
    if record_type == "status_update":
        node = data.get("node", "unknown")
        return f"State update: {node}"
    return ""
