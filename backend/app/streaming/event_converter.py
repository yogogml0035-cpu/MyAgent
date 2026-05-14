"""Convert LangGraph stream events to MyAgent event records."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from app.schemas import EventRecord

# Mapping from adapter event type to EventRecord type string.
_TYPE_MAP: dict[str, str] = {
    "thinking_chunk": "assistant_thinking_delta",
    "message_chunk": "assistant_answer_delta",
    "tool_call": "tool_call",
    "tool_result": "tool_result",
    "state_update": "status_update",
    "values_snapshot": "values_snapshot",
}

# Default level per event type.
_LEVEL_MAP: dict[str, Literal["info", "success", "warning", "error"]] = {
    "assistant_thinking_delta": "info",
    "assistant_answer_delta": "info",
    "tool_call": "info",
    "tool_result": "info",
    "status_update": "info",
    "values_snapshot": "info",
}

_MAX_PARAMETER_ITEMS = 8
_MAX_PARAMETER_TEXT = 160


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
    raw_data = event.get("data", {})
    data = raw_data if isinstance(raw_data, dict) else {}

    record_type = _TYPE_MAP.get(event_type) if event_type is not None else None
    if record_type is None:
        return None

    message = _build_message(record_type, data)
    level = _LEVEL_MAP.get(record_type, "info")

    if record_type == "assistant_thinking_delta":
        payload = {
            "schema_version": 1,
            "stream_index": seq or 0,
            "content": data.get("content", ""),
            "is_subgraph": data.get("is_subgraph", False),
            "live": {
                "schema_version": 1,
                "kind": "think",
                "stage": "thinking",
                "display_text": "AI正在思考...",
                "diagnostic_label": "model.reasoning_content",
                "parameter_items": [
                    {"key": "is_subgraph", "value": bool(data.get("is_subgraph", False))},
                ],
            },
        }
    elif record_type == "assistant_answer_delta":
        payload = {
            "schema_version": 1,
            "stream_index": seq or 0,
            "content": data.get("content", ""),
            "is_subgraph": data.get("is_subgraph", False),
        }
    elif record_type == "values_snapshot":
        payload = {
            "snapshot_keys": list(data.keys()) if isinstance(data, dict) else [],
            "is_subgraph": data.get("is_subgraph", False),
        }
    else:
        payload = {**data, "live": _build_live_metadata(record_type, data)}

    return EventRecord(
        id=str(uuid.uuid4()),
        session_id=task_id,
        seq=seq,
        type=record_type,
        message=message,
        created_at=datetime.now(tz=timezone.utc).isoformat(),
        payload=payload,
        run_id=run_id,
        level=level,
    )


def _build_message(record_type: str, data: dict[str, Any]) -> str:
    if record_type == "assistant_thinking_delta":
        return data.get("content", "")
    if record_type == "assistant_answer_delta":
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
    if record_type == "values_snapshot":
        return "State snapshot"
    return ""


def _build_live_metadata(record_type: str, data: dict[str, Any]) -> dict[str, Any]:
    if record_type == "tool_call":
        tool_name = _safe_string(data.get("name"), "tool")
        partial = bool(data.get("partial", False))
        return {
            "schema_version": 1,
            "kind": "tool_call",
            "stage": "selecting_tool" if partial else "using_tool",
            "tool_name": tool_name,
            "tool_label": _tool_label(tool_name),
            "tool_call_id": _safe_string(data.get("id")),
            "parameter_items": _parameter_items(data.get("args")),
            "diagnostic_label": "tool_call_delta" if partial else "tool_call",
        }

    if record_type == "tool_result":
        tool_name = _safe_string(data.get("name"), "tool")
        status = _safe_string(data.get("status"), "success")
        return {
            "schema_version": 1,
            "kind": "tool_result",
            "stage": "completed",
            "tool_name": tool_name,
            "tool_label": _tool_label(tool_name),
            "tool_call_id": _safe_string(data.get("tool_call_id")),
            "parameter_items": [],
            "result_status": _tool_result_status(status),
        }

    if record_type == "status_update":
        node = _safe_string(data.get("node"), "unknown")
        stage, display_text = _status_update_stage(node)
        return {
            "schema_version": 1,
            "kind": "status",
            "stage": stage,
            "agent_name": node,
            "display_text": display_text,
            "diagnostic_label": node,
            "parameter_items": [
                {"key": "node", "value": node},
                {"key": "is_subgraph", "value": bool(data.get("is_subgraph", False))},
            ],
        }

    return {
        "schema_version": 1,
        "kind": "status",
        "stage": "organizing_state",
        "parameter_items": [],
    }


def _safe_string(value: Any, fallback: str = "") -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return fallback
    return str(value)


def _tool_label(tool_name: str) -> str:
    normalized = tool_name.lower()
    if "resource" in normalized or normalized in {
        "list_uploaded_resources",
        "inspect_resource",
        "read_resource_text",
        "read_resource_table",
    }:
        return "处理资源文件"
    if "tavily" in normalized or "search" in normalized:
        return "联网搜索"
    if normalized in {"read_file", "read"} or "read_file" in normalized:
        return "读取文件"
    if normalized in {"write_file", "write"} or "write_file" in normalized:
        return "写入文件"
    if normalized in {"list_files", "list_dir", "ls"} or "list" in normalized:
        return "查看文件列表"
    return "调用工具"


def _tool_result_status(status: str) -> Literal["success", "empty", "failed", "cancelled", "skipped"]:
    normalized = status.lower()
    if normalized in {"success", "ok"}:
        return "success"
    if normalized in {"empty", "not_found", "no_results"}:
        return "empty"
    if normalized in {"cancelled", "canceled"}:
        return "cancelled"
    if normalized == "skipped":
        return "skipped"
    return "failed"


def _parameter_items(raw_args: Any) -> list[dict[str, Any]]:
    args = _coerce_args(raw_args)
    if isinstance(args, dict):
        items: list[dict[str, Any]] = []
        for key, value in args.items():
            if len(items) >= _MAX_PARAMETER_ITEMS:
                break
            normalized = _parameter_value(value)
            if normalized is None:
                continue
            items.append({"key": str(key), **normalized})
        return items

    normalized = _parameter_value(args)
    return [{"key": "args", **normalized}] if normalized is not None else []


def _coerce_args(raw_args: Any) -> Any:
    if not isinstance(raw_args, str):
        return raw_args
    text = raw_args.strip()
    if not text:
        return raw_args
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return raw_args


def _parameter_value(value: Any) -> dict[str, Any] | None:
    if isinstance(value, (bool, int, float)):
        return {"value": value}
    if isinstance(value, str):
        truncated = len(value) > _MAX_PARAMETER_TEXT
        display_value = value[:_MAX_PARAMETER_TEXT] if truncated else value
        return {"value": display_value, "truncated": truncated}
    if value is None:
        return None

    text = json.dumps(value, ensure_ascii=False, default=str)
    truncated = len(text) > _MAX_PARAMETER_TEXT
    display_value = text[:_MAX_PARAMETER_TEXT] if truncated else text
    return {"value": display_value, "truncated": truncated}


def _status_update_stage(node: str) -> tuple[str, str]:
    normalized = node.lower()
    if "before_agent" in normalized or "middleware" in normalized:
        return "preparing", "正在准备任务..."
    if normalized == "model" or normalized.endswith(":model") or "after_model" in normalized:
        return "thinking", "AI正在思考..."
    if normalized in {"tools", "tool"} or "tool" in normalized:
        return "organizing_state", "正在整理工具结果..."
    if "final" in normalized or "answer" in normalized:
        return "generating_answer", "AI正在生成结果"
    if "state" in normalized or "todo" in normalized or "values" in normalized:
        return "organizing_state", "正在整理任务状态..."
    return "organizing_state", "正在整理任务状态..."
