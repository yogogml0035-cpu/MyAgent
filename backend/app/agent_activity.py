from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from contextlib import suppress
from math import isfinite
from typing import Any, Literal, TypeAlias

from .reasoning_trace import sanitize_reasoning_text

ActivityKind: TypeAlias = Literal["lifecycle", "progress"]
ActivityPhase: TypeAlias = Literal[
    "planning", "reasoning", "tool_use", "file_operation", "finalizing"
]
ActivityStatus: TypeAlias = Literal["started", "running", "completed", "failed", "skipped"]
ActivitySink: TypeAlias = Callable[[dict[str, Any]], Any]

ACTIVITY_KINDS = {"lifecycle", "progress"}
ACTIVITY_PHASES = {"planning", "reasoning", "tool_use", "file_operation", "finalizing"}
ACTIVITY_STATUSES = {"started", "running", "completed", "failed", "skipped"}
STREAM_MODES = {"updates", "messages", "custom"}
BOUNDARY_STATUSES = {"started", "completed", "failed", "skipped"}
SENSITIVE_KEY_PATTERN = re.compile(
    r"(?:api[_-]?key|secret|token|authorization|password|credential|content|prompt|body|result)",
    re.IGNORECASE,
)
INTERNAL_PATH_PATTERN = re.compile(
    r"/?(?:conversation_history|large_tool_results)(?:/[^\s\"'，。；;]*)?",
    re.IGNORECASE,
)
SAFE_VIRTUAL_ROOTS = {"uploads", "records", "outputs"}
MAX_PAYLOAD_BYTES = 8 * 1024
MAX_LIVE_PARAMETER_ITEMS = 5
MAX_LIVE_PARAMETER_KEY_CHARS = 40
MAX_LIVE_PARAMETER_STRING_CHARS = 80
MAX_LIVE_ID_CHARS = 120
SAFE_TOOL_RESULT_STATUSES = {
    "success",
    "ok",
    "completed",
    "complete",
    "failed",
    "failure",
    "error",
    "denied",
    "cancelled",
    "skipped",
    "timeout",
}
LIVE_KINDS = {"think", "tool_call", "tool_result", "answer_status", "status"}
LIVE_STAGES = {
    "analyzing_intent",
    "selecting_tool",
    "using_tool",
    "reading_input",
    "generating_answer",
    "completed",
    "needs_input",
    "failed",
}
LIVE_RESULT_STATUSES = {"success", "empty", "failed", "cancelled", "skipped"}
LIVE_SAFE_PARAMETER_KEYS = {"max_results"}
LIVE_SECRET_KEY_PATTERN = re.compile(
    r"(?:api[_-]?key|secret|token|authorization|auth|password|credential|content|prompt|body|result)",
    re.IGNORECASE,
)
LIVE_RESULT_COUNT_KEYS = ("result_count", "count", "total_count", "total", "items_count")
LIVE_RESULT_LIST_KEYS = ("results", "items", "records", "sources")
LIVE_PATH_PARAMETER_KEYS = {"path", "file_path", "relative_path", "virtual_path"}
LIVE_PARAMETER_PRIORITY = (
    "query",
    "max_results",
    "use_uploads",
    "relative_path",
    "virtual_path",
    "path",
    "file_path",
)

FIELD_LIMITS = {
    "title": 120,
    "summary": 1000,
    "tool_name": 80,
    "parameter_summary": 240,
    "result_summary": 360,
    "source_event_id": 160,
    "related_event_id": 160,
    "subgraph_path": 80,
    "agent_id": 120,
    "parent_agent_id": 120,
    "task_label": 160,
}


def build_deep_agent_activity_payload(
    *,
    activity_kind: str,
    phase: str,
    status: str,
    title: str,
    summary: str | None = None,
    tool_name: str | None = None,
    parameter_summary: str | None = None,
    result_summary: str | None = None,
    subgraph_path: Iterable[Any] | None = None,
    source_event_id: str | None = None,
    related_event_id: str | None = None,
    agent_id: str | None = None,
    parent_agent_id: str | None = None,
    task_label: str | None = None,
    live: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_kind = activity_kind.strip() if isinstance(activity_kind, str) else ""
    normalized_phase = phase.strip() if isinstance(phase, str) else ""
    normalized_status = status.strip() if isinstance(status, str) else ""
    if normalized_kind not in ACTIVITY_KINDS:
        raise ValueError(f"deep_agent_activity.activity_kind 无效：{activity_kind}")
    if normalized_phase not in ACTIVITY_PHASES:
        raise ValueError(f"deep_agent_activity.phase 无效：{phase}")
    if normalized_status not in ACTIVITY_STATUSES:
        raise ValueError(f"deep_agent_activity.status 无效：{status}")

    payload: dict[str, Any] = {
        "schema_version": 1,
        "source": "deepagents",
        "activity_kind": normalized_kind,
        "phase": normalized_phase,
        "status": normalized_status,
        "truncated": False,
    }
    payload["title"], title_truncated = _sanitize_activity_text(
        title, max_chars=FIELD_LIMITS["title"]
    )
    if not payload["title"]:
        raise ValueError("deep_agent_activity.title 不能为空")
    payload["truncated"] = payload["truncated"] or title_truncated
    payload["summary"], summary_truncated = _sanitize_activity_text(
        summary, max_chars=FIELD_LIMITS["summary"]
    )
    if not payload["summary"]:
        raise ValueError("deep_agent_activity.summary 不能为空")
    payload["truncated"] = payload["truncated"] or summary_truncated

    optional_fields = {
        "tool_name": tool_name,
        "parameter_summary": parameter_summary,
        "result_summary": result_summary,
        "source_event_id": source_event_id,
        "related_event_id": related_event_id,
        "agent_id": agent_id,
        "parent_agent_id": parent_agent_id,
        "task_label": task_label,
    }
    for field, value in optional_fields.items():
        if value is None:
            continue
        sanitized, truncated = _sanitize_activity_text(
            value, max_chars=FIELD_LIMITS[field]
        )
        if sanitized:
            payload[field] = sanitized
            payload["truncated"] = payload["truncated"] or truncated

    path, path_truncated = _sanitize_subgraph_path(subgraph_path or [])
    if path:
        payload["subgraph_path"] = path
        payload["truncated"] = payload["truncated"] or path_truncated
    normalized_live = normalize_live_metadata(live)
    if normalized_live is not None:
        payload["live"] = normalized_live

    if len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) > MAX_PAYLOAD_BYTES:
        payload["summary"] = _trim_text(str(payload.get("summary") or ""), 360)
        payload["result_summary"] = _trim_text(str(payload.get("result_summary") or ""), 240)
        payload["truncated"] = True
    return payload


def build_live_tool_call_metadata(
    *,
    agent_name: str,
    tool_name: str,
    tool_call_id: str,
    parameters: Any,
) -> dict[str, Any]:
    return normalize_live_metadata(
        {
            "schema_version": 1,
            "kind": "tool_call",
            "stage": "using_tool",
            "agent_name": agent_name,
            "tool_name": tool_name,
            "tool_call_id": tool_call_id,
            "parameter_items": _live_parameter_items(parameters),
        }
    ) or {"schema_version": 1, "kind": "tool_call"}


def build_live_tool_result_metadata(
    *,
    agent_name: str,
    tool_name: str,
    tool_call_id: str,
    result: Any,
    result_status: str | None = None,
    result_count: int | None = None,
) -> dict[str, Any]:
    resolved_status = _normalize_live_result_status(result_status)
    if resolved_status is None:
        resolved_status = _infer_live_result_status(result)
    resolved_count = result_count if isinstance(result_count, int) and result_count >= 0 else None
    if resolved_count is None:
        resolved_count = _infer_live_result_count(result)
    metadata: dict[str, Any] = {
        "schema_version": 1,
        "kind": "tool_result",
        "stage": "completed" if resolved_status != "failed" else "failed",
        "agent_name": agent_name,
        "tool_name": tool_name,
        "tool_call_id": tool_call_id,
        "result_status": resolved_status,
    }
    if resolved_count is not None:
        metadata["result_count"] = resolved_count
    return normalize_live_metadata(metadata) or {
        "schema_version": 1,
        "kind": "tool_result",
        "result_status": resolved_status,
    }


def build_live_answer_status_metadata(
    *,
    agent_name: str,
    stage: str,
    result_status: str | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "schema_version": 1,
        "kind": "answer_status",
        "stage": stage,
        "agent_name": agent_name,
    }
    normalized_status = _normalize_live_result_status(result_status)
    if normalized_status is not None:
        metadata["result_status"] = normalized_status
    return normalize_live_metadata(metadata) or {
        "schema_version": 1,
        "kind": "answer_status",
    }


def build_live_status_metadata(
    *,
    agent_name: str,
    stage: str,
    result_status: str | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "schema_version": 1,
        "kind": "status",
        "stage": stage,
        "agent_name": agent_name,
    }
    normalized_status = _normalize_live_result_status(result_status)
    if normalized_status is not None:
        metadata["result_status"] = normalized_status
    return normalize_live_metadata(metadata) or {"schema_version": 1, "kind": "status"}


def normalize_live_metadata(value: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    if value.get("schema_version") != 1:
        return None
    kind = value.get("kind")
    if not isinstance(kind, str) or kind not in LIVE_KINDS:
        return None
    live: dict[str, Any] = {"schema_version": 1, "kind": kind}
    stage = value.get("stage")
    if isinstance(stage, str) and stage in LIVE_STAGES:
        live["stage"] = stage
    for field in ("agent_name", "tool_name", "tool_call_id"):
        text, _ = _sanitize_activity_text(
            value.get(field), max_chars=MAX_LIVE_ID_CHARS
        )
        if text:
            live[field] = text
    parameter_items = value.get("parameter_items")
    if isinstance(parameter_items, Sequence) and not isinstance(
        parameter_items, (str, bytes, bytearray)
    ):
        items: list[dict[str, Any]] = []
        for item in parameter_items:
            normalized_item = _normalize_live_parameter_item(item)
            if normalized_item is not None:
                items.append(normalized_item)
            if len(items) >= MAX_LIVE_PARAMETER_ITEMS:
                break
        if items:
            live["parameter_items"] = items
    result_status = _normalize_live_result_status(value.get("result_status"))
    if result_status is not None:
        live["result_status"] = result_status
    result_count = value.get("result_count")
    if isinstance(result_count, int) and result_count >= 0:
        live["result_count"] = result_count
    return live


def validate_deep_agent_activity_payload(payload: Mapping[str, Any]) -> bool:
    try:
        build_deep_agent_activity_payload(
            activity_kind=str(payload.get("activity_kind") or ""),
            phase=str(payload.get("phase") or ""),
            status=str(payload.get("status") or ""),
            title=str(payload.get("title") or ""),
            summary=_optional_str(payload.get("summary")),
            tool_name=_optional_str(payload.get("tool_name")),
            parameter_summary=_optional_str(payload.get("parameter_summary")),
            result_summary=_optional_str(payload.get("result_summary")),
            subgraph_path=payload.get("subgraph_path")
            if isinstance(payload.get("subgraph_path"), Iterable)
            and not isinstance(payload.get("subgraph_path"), (str, bytes))
            else [],
            source_event_id=_optional_str(payload.get("source_event_id")),
            related_event_id=_optional_str(payload.get("related_event_id")),
            agent_id=_optional_str(payload.get("agent_id")),
            parent_agent_id=_optional_str(payload.get("parent_agent_id")),
            task_label=_optional_str(payload.get("task_label")),
            live=payload.get("live") if isinstance(payload.get("live"), Mapping) else None,
        )
    except ValueError:
        return False
    return payload.get("schema_version") == 1 and payload.get("source") == "deepagents"


class DeepAgentActivityProjector:
    """Project DeepAgents stream chunks into MyAgent's stable safe event contract."""

    def __init__(
        self,
        *,
        task_id: str,
        run_id: str,
        sink: ActivitySink | None,
        coalesce_seconds: float = 1.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.task_id = task_id
        self.run_id = run_id
        self.sink = sink
        self.coalesce_seconds = coalesce_seconds
        self.clock = clock
        self._counter = 0
        self._tool_call_counter = 0
        self._pending_tool_calls: dict[str, str] = {}
        self._pending_tool_call_order: list[str] = []
        self._last_emit_at: dict[tuple[str, str, tuple[str, ...], str, str], float] = {}
        self._assistant_message_id: str | None = None
        self._assistant_parts: list[str] = []
        self._final_assistant_text = ""
        self._answer_generation_paths: set[tuple[str, ...]] = set()

    @property
    def final_output_text(self) -> str:
        buffered = "".join(self._assistant_parts).strip()
        return buffered or self._final_assistant_text.strip()

    def record_final_output_text(self, output_text: str) -> None:
        text = output_text.strip()
        if text:
            self._final_assistant_text = text

    def emit_started(self) -> None:
        self.emit(
            activity_kind="lifecycle",
            phase="planning",
            status="started",
            title="DeepAgent 已启动",
            summary="DeepAgent 已在本轮隔离工作区内开始执行。",
            live=build_live_status_metadata(
                agent_name="deep_agent",
                stage="analyzing_intent",
            ),
        )

    def emit_completed(self) -> None:
        self.emit(
            activity_kind="lifecycle",
            phase="finalizing",
            status="completed",
            title="DeepAgent 已完成",
            summary="DeepAgent 执行结束，最终回复将作为单独助手消息保存。",
            live=(
                build_live_answer_status_metadata(
                    agent_name="deep_agent",
                    stage="completed",
                    result_status="success",
                )
                if self.final_output_text
                else build_live_status_metadata(
                    agent_name="deep_agent",
                    stage="completed",
                    result_status="success",
                )
            ),
        )

    def emit_failed(self) -> None:
        self.emit(
            activity_kind="lifecycle",
            phase="finalizing",
            status="failed",
            title="DeepAgent 执行失败",
            summary="DeepAgent 执行未完成，已停止记录流式进度。",
            live=build_live_status_metadata(
                agent_name="deep_agent",
                stage="failed",
                result_status="failed",
            ),
        )

    def emit_invoke_fallback(self) -> None:
        self.emit(
            activity_kind="progress",
            phase="planning",
            status="skipped",
            title="DeepAgent 流式进度不可用",
            summary="当前 DeepAgents 对象未提供兼容的 stream 接口，已改用一次性调用并保留安全执行记录。",
            live=build_live_answer_status_metadata(
                agent_name="deep_agent",
                stage="generating_answer",
            ),
        )

    def observe_stream_chunk(self, chunk: Any) -> None:
        mode, data, subgraph_path = _split_stream_chunk(chunk)
        if mode == "messages":
            self._observe_message_data(data, subgraph_path)
            return
        if mode == "updates":
            self._observe_update_data(data, subgraph_path)
            return
        if mode == "custom":
            self._observe_custom_data(data, subgraph_path)
            return
        self.emit(
            activity_kind="progress",
            phase="reasoning",
            status="running",
            title="DeepAgent 正在运行",
            summary="收到 DeepAgent 进度更新。",
            subgraph_path=subgraph_path,
        )

    def emit(
        self,
        *,
        activity_kind: str,
        phase: str,
        status: str,
        title: str,
        summary: str | None = None,
        tool_name: str | None = None,
        parameter_summary: str | None = None,
        result_summary: str | None = None,
        subgraph_path: Iterable[Any] | None = None,
        related_event_id: str | None = None,
        live: Mapping[str, Any] | None = None,
    ) -> None:
        if self.sink is None:
            return
        path = tuple(_sanitize_subgraph_path(subgraph_path or [])[0])
        signature = (self.task_id, self.run_id, path, str(phase), str(status))
        now = self.clock()
        if status not in BOUNDARY_STATUSES:
            last_emit_at = self._last_emit_at.get(signature)
            if last_emit_at is not None and now - last_emit_at < self.coalesce_seconds:
                return
        self._last_emit_at[signature] = now
        self._counter += 1
        payload = build_deep_agent_activity_payload(
            activity_kind=activity_kind,
            phase=phase,
            status=status,
            title=title,
            summary=summary,
            tool_name=tool_name,
            parameter_summary=parameter_summary,
            result_summary=result_summary,
            subgraph_path=path,
            source_event_id=f"dg_evt_{self._counter}",
            related_event_id=related_event_id,
            agent_id=_agent_id_from_path(path),
            task_label=_task_label_from_path(path),
            live=live,
        )
        self.sink(payload)

    def _observe_update_data(self, data: Any, subgraph_path: list[str]) -> None:
        self._observe_nested_messages(data, subgraph_path)
        if isinstance(data, Mapping):
            keys = [
                key
                for key in (str(key) for key in data)
                if key and not key.startswith("__")
            ][:4]
            title = "DeepAgent 进度更新"
            summary = "DeepAgent 已更新运行状态。"
            phase = "reasoning"
            if keys:
                safe_keys = [
                    _sanitize_activity_text(key, max_chars=48)[0] for key in keys
                ]
                safe_keys = [key for key in safe_keys if key]
                if safe_keys:
                    summary = f"节点 {', '.join(safe_keys)} 已产生进度更新。"
                    if any("tool" in key.lower() for key in safe_keys):
                        phase = "tool_use"
            self.emit(
                activity_kind="progress",
                phase=phase,
                status="running",
                title=title,
                summary=summary,
                subgraph_path=subgraph_path,
            )
            return
        self.emit(
            activity_kind="progress",
            phase="reasoning",
            status="running",
            title="DeepAgent 进度更新",
            summary="DeepAgent 已更新运行状态。",
            subgraph_path=subgraph_path,
        )

    def _observe_custom_data(self, data: Any, subgraph_path: list[str]) -> None:
        agent_name = _agent_name_from_path(subgraph_path)
        title = "自定义进度"
        summary = "收到自定义进度事件。"
        if isinstance(data, Mapping):
            status = str(data.get("status") or "")
            if status:
                title = f"自定义进度：{status}"
            topic = str(data.get("topic") or data.get("message") or "")
            if topic:
                summary = topic[:200]
        elif isinstance(data, str):
            summary = data[:200]
        self.emit(
            activity_kind="progress",
            phase="tool_use",
            status="running",
            title=title,
            summary=summary,
            subgraph_path=subgraph_path,
            live=build_live_status_metadata(
                agent_name=agent_name,
                stage="using_tool",
            ),
        )

    def _observe_message_data(self, data: Any, subgraph_path: list[str]) -> None:
        message = data
        if isinstance(data, tuple) and data:
            message = data[0]
        if isinstance(message, Sequence) and not isinstance(message, (str, bytes, bytearray)):
            for item in message:
                self._observe_message_data(item, subgraph_path)
            return
        self._observe_message(message, subgraph_path)

    def _observe_nested_messages(self, data: Any, subgraph_path: list[str]) -> None:
        if isinstance(data, Mapping):
            messages = data.get("messages")
            if isinstance(messages, Sequence) and not isinstance(messages, (str, bytes)):
                for message in messages:
                    self._observe_message(message, subgraph_path)
            for key, value in data.items():
                if key == "messages":
                    continue
                if isinstance(value, Mapping):
                    nested_path = [*subgraph_path, str(key)]
                    self._observe_nested_messages(value, nested_path)
        elif isinstance(data, Sequence) and not isinstance(data, (str, bytes, bytearray)):
            for item in data:
                self._observe_nested_messages(item, subgraph_path)

    def _observe_message(self, message: Any, subgraph_path: list[str]) -> None:
        agent_name = _agent_name_from_path(subgraph_path)
        for tool_call in _extract_tool_calls(message):
            tool_name = _tool_call_name(tool_call)
            tool_args = _tool_call_args(tool_call)
            tool_call_id = self._resolve_tool_call_id(tool_call, tool_name)
            self.emit(
                activity_kind="lifecycle",
                phase="tool_use",
                status="started",
                title="工具调用准备",
                summary=f"DeepAgent 准备调用 {tool_name or '工具'}。",
                tool_name=tool_name,
                parameter_summary=_summarize_tool_arguments(tool_args),
                subgraph_path=subgraph_path,
                live=build_live_tool_call_metadata(
                    agent_name=agent_name,
                    tool_name=tool_name,
                    tool_call_id=tool_call_id,
                    parameters=tool_args,
                ),
            )

        if _is_tool_message(message):
            tool_name = _message_tool_name(message)
            content = _message_content(message)
            tool_call_id = self._resolve_tool_result_id(message, tool_name)
            live_result_status = _tool_message_live_result_status(message)
            self.emit(
                activity_kind="lifecycle",
                phase="tool_use",
                status=_tool_message_status(message),
                title="工具调用完成",
                summary=f"DeepAgent 已收到 {tool_name or '工具'} 的执行结果。",
                tool_name=tool_name,
                result_summary=_summarize_tool_result(content),
                subgraph_path=subgraph_path,
                live=build_live_tool_result_metadata(
                    agent_name=agent_name,
                    tool_name=tool_name,
                    tool_call_id=tool_call_id,
                    result=content,
                    result_status=live_result_status,
                ),
            )
            return

        if not _is_assistant_message(message) or _extract_tool_calls(message):
            return
        content = _message_content_text(message).strip()
        if not content:
            return
        self._emit_answer_generation_started(agent_name, subgraph_path)
        message_id = _message_id(message)
        if _is_chunk_message(message):
            if message_id and self._assistant_message_id not in {None, message_id}:
                self._assistant_parts = []
            self._assistant_message_id = message_id or self._assistant_message_id
            self._assistant_parts.append(content)
            return
        self._assistant_message_id = message_id
        self._assistant_parts = [content]
        self._final_assistant_text = content

    def _emit_answer_generation_started(
        self, agent_name: str, subgraph_path: list[str]
    ) -> None:
        path = tuple(_sanitize_subgraph_path(subgraph_path)[0])
        if path in self._answer_generation_paths:
            return
        self._answer_generation_paths.add(path)
        self.emit(
            activity_kind="progress",
            phase="finalizing",
            status="running",
            title="正在生成回答",
            summary="DeepAgent 正在整理最终回复。",
            subgraph_path=subgraph_path,
            live=build_live_answer_status_metadata(
                agent_name=agent_name,
                stage="generating_answer",
            ),
        )

    def _resolve_tool_call_id(self, tool_call: Any, tool_name: str) -> str:
        tool_call_id = _tool_call_id(tool_call) or self._next_tool_call_id()
        self._remember_tool_call(tool_call_id, tool_name)
        return tool_call_id

    def _resolve_tool_result_id(self, message: Any, tool_name: str) -> str:
        tool_call_id = _message_tool_call_id(message)
        if tool_call_id:
            self._forget_tool_call(tool_call_id)
            return tool_call_id
        pending = self._pop_pending_tool_call(tool_name)
        return pending or self._next_tool_call_id()

    def _next_tool_call_id(self) -> str:
        self._tool_call_counter += 1
        return f"dg_tool_{self._tool_call_counter}"

    def _remember_tool_call(self, tool_call_id: str, tool_name: str) -> None:
        self._pending_tool_calls[tool_call_id] = tool_name
        if tool_call_id not in self._pending_tool_call_order:
            self._pending_tool_call_order.append(tool_call_id)

    def _forget_tool_call(self, tool_call_id: str) -> None:
        self._pending_tool_calls.pop(tool_call_id, None)
        with suppress(ValueError):
            self._pending_tool_call_order.remove(tool_call_id)

    def _pop_pending_tool_call(self, tool_name: str) -> str | None:
        for tool_call_id in list(self._pending_tool_call_order):
            if self._pending_tool_calls.get(tool_call_id) == tool_name:
                self._forget_tool_call(tool_call_id)
                return tool_call_id
        if not self._pending_tool_call_order:
            return None
        tool_call_id = self._pending_tool_call_order[0]
        self._forget_tool_call(tool_call_id)
        return tool_call_id


def activity_payload_from_file_audit(
    audit_payload: Mapping[str, Any],
    *,
    related_event_id: str,
) -> dict[str, Any]:
    status = str(audit_payload.get("status") or "unknown")
    operation = str(audit_payload.get("op") or audit_payload.get("operation") or "file")
    virtual_path = _safe_virtual_path(
        audit_payload.get("virtual_path") or audit_payload.get("relative_path")
    )
    title = "文件操作审计"
    summary = f"DeepAgent 文件操作 {operation} 已记录为 {status}。"
    if virtual_path:
        summary = f"DeepAgent 文件操作 {operation} 已记录为 {status}：{virtual_path}。"
    result_parts = [f"status={status}"]
    bytes_count = audit_payload.get("bytes")
    if isinstance(bytes_count, int):
        result_parts.append(f"bytes={bytes_count}")
    sha256 = audit_payload.get("sha256")
    if isinstance(sha256, str) and sha256:
        result_parts.append(f"sha256={sha256[:12]}")
    source = audit_payload.get("source")
    if isinstance(source, str) and source:
        result_parts.append(f"source={source}")
    promoted = audit_payload.get("promoted_artifact_id")
    if isinstance(promoted, str) and promoted:
        safe_promoted, _ = _sanitize_activity_text(promoted, max_chars=80)
        if safe_promoted:
            result_parts.append(f"promoted_artifact_id={safe_promoted}")
    return build_deep_agent_activity_payload(
        activity_kind="lifecycle",
        phase="file_operation",
        status="completed" if status == "success" else "failed",
        title=title,
        summary=summary,
        tool_name=_optional_str(audit_payload.get("tool_name") or audit_payload.get("tool")),
        parameter_summary=f"virtual_path={virtual_path}" if virtual_path else "virtual_path=<redacted>",
        result_summary="; ".join(result_parts),
        related_event_id=related_event_id,
        source_event_id=f"audit_{related_event_id}",
    )


def _split_stream_chunk(chunk: Any) -> tuple[str | None, Any, list[str]]:
    if isinstance(chunk, Mapping):
        chunk_type = chunk.get("type")
        if chunk_type in STREAM_MODES:
            return chunk_type, chunk.get("data"), _path_items(chunk.get("ns"))
        if chunk_type is not None:
            return None, chunk, []
    if isinstance(chunk, tuple):
        if len(chunk) == 3 and isinstance(chunk[1], str) and chunk[1] in STREAM_MODES:
            return chunk[1], chunk[2], _path_items(chunk[0])
        if len(chunk) == 2 and isinstance(chunk[0], str) and chunk[0] in STREAM_MODES:
            return chunk[0], chunk[1], []
        if (
            len(chunk) == 2
            and isinstance(chunk[0], (tuple, list))
            and isinstance(chunk[1], tuple)
            and len(chunk[1]) == 2
            and isinstance(chunk[1][0], str)
            and chunk[1][0] in STREAM_MODES
        ):
            return chunk[1][0], chunk[1][1], _path_items(chunk[0])
        if len(chunk) == 2 and isinstance(chunk[0], (tuple, list)):
            return _infer_mode(chunk[1]), chunk[1], _path_items(chunk[0])
    return _infer_mode(chunk), chunk, []


def _infer_mode(data: Any) -> str | None:
    if isinstance(data, tuple) and data and _looks_like_message(data[0]):
        return "messages"
    if _looks_like_message(data):
        return "messages"
    return None


def _path_items(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Iterable):
        items: list[str] = []
        for item in value:
            if isinstance(item, (tuple, list)):
                items.extend(_path_items(item))
            else:
                items.append(str(item))
        return items
    return []


def _agent_id_from_path(path: Sequence[str]) -> str | None:
    for item in reversed(path):
        sanitized, _ = _sanitize_activity_text(item, max_chars=FIELD_LIMITS["agent_id"])
        if sanitized and sanitized not in {"updates", "messages"}:
            return sanitized
    return None


def _agent_name_from_path(path: Sequence[str]) -> str:
    return _agent_id_from_path(path) or "main_agent"


def _task_label_from_path(path: Sequence[str]) -> str | None:
    agent_id = _agent_id_from_path(path)
    if not agent_id:
        return None
    label = agent_id.removesuffix("-agent").replace("-", " ").strip()
    sanitized, _ = _sanitize_activity_text(label, max_chars=FIELD_LIMITS["task_label"])
    return sanitized or None


def _extract_tool_calls(message: Any) -> list[Any]:
    tool_calls = _message_value(message, "tool_calls")
    if tool_calls is None:
        additional_kwargs = _message_value(message, "additional_kwargs")
        if isinstance(additional_kwargs, Mapping):
            tool_calls = additional_kwargs.get("tool_calls")
    if isinstance(tool_calls, Sequence) and not isinstance(tool_calls, (str, bytes)):
        return list(tool_calls)
    return []


def _tool_call_name(tool_call: Any) -> str:
    name = _mapping_or_attr(tool_call, "name") or _mapping_or_attr(tool_call, "tool_name")
    if not name:
        function = _mapping_or_attr(tool_call, "function")
        if isinstance(function, Mapping):
            name = function.get("name")
    sanitized, _ = _sanitize_activity_text(str(name or "tool"), max_chars=FIELD_LIMITS["tool_name"])
    return sanitized or "tool"


def _tool_call_args(tool_call: Any) -> Any:
    args = _mapping_or_attr(tool_call, "args")
    if args is not None:
        return args
    function = _mapping_or_attr(tool_call, "function")
    if isinstance(function, Mapping):
        return function.get("arguments")
    return None


def _tool_call_id(tool_call: Any) -> str | None:
    for key in ("id", "tool_call_id"):
        value = _mapping_or_attr(tool_call, key)
        safe_id = _safe_live_id(value)
        if safe_id:
            return safe_id
    function = _mapping_or_attr(tool_call, "function")
    if isinstance(function, Mapping):
        for key in ("id", "tool_call_id"):
            safe_id = _safe_live_id(function.get(key))
            if safe_id:
                return safe_id
    return None


def _message_tool_call_id(message: Any) -> str | None:
    for key in ("tool_call_id", "id"):
        safe_id = _safe_live_id(_message_value(message, key))
        if safe_id:
            return safe_id
    return None


def _safe_live_id(value: Any) -> str | None:
    if value is None:
        return None
    sanitized, _ = _sanitize_activity_text(value, max_chars=MAX_LIVE_ID_CHARS)
    return sanitized or None


def _live_parameter_items(parameters: Any) -> list[dict[str, Any]]:
    normalized_parameters = _mapping_from_json_string(parameters)
    if not isinstance(normalized_parameters, Mapping):
        return []

    ordered_keys = [key for key in LIVE_PARAMETER_PRIORITY if key in normalized_parameters]
    ordered_keys.extend(
        str(key)
        for key in normalized_parameters
        if isinstance(key, str) and key not in ordered_keys
    )

    items: list[dict[str, Any]] = []
    for key in ordered_keys:
        normalized_item = _normalize_live_parameter_item(
            {"key": key, "value": normalized_parameters.get(key)}
        )
        if normalized_item is not None:
            items.append(normalized_item)
        if len(items) >= MAX_LIVE_PARAMETER_ITEMS:
            break
    return items


def _normalize_live_parameter_item(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, Mapping):
        return None
    raw_key = item.get("key")
    if not isinstance(raw_key, str):
        return None
    if raw_key not in LIVE_SAFE_PARAMETER_KEYS and LIVE_SECRET_KEY_PATTERN.search(raw_key):
        return None
    key, key_truncated = _sanitize_activity_text(
        raw_key, max_chars=MAX_LIVE_PARAMETER_KEY_CHARS
    )
    if not key:
        return None
    if key not in LIVE_SAFE_PARAMETER_KEYS and LIVE_SECRET_KEY_PATTERN.search(key):
        return None

    input_truncated = item.get("truncated") is True
    normalized: dict[str, Any] = {"key": key}
    value = item.get("value")
    if isinstance(value, (bool, int)) or (isinstance(value, float) and isfinite(value)):
        normalized["value"] = value
    elif isinstance(value, str):
        parameter_value, value_truncated = _safe_live_parameter_string(key, value)
        if parameter_value is None:
            return None
        normalized["value"] = parameter_value
        if key_truncated or value_truncated or input_truncated:
            normalized["truncated"] = True
        return normalized
    else:
        return None

    if key_truncated or input_truncated:
        normalized["truncated"] = True
    return normalized


def _safe_live_parameter_string(key: str, value: str) -> tuple[str | None, bool]:
    if key in LIVE_PATH_PARAMETER_KEYS:
        safe_path = _safe_virtual_path(value)
        if safe_path:
            return safe_path, False
        return "<redacted>", True

    raw = value.strip()
    if not raw:
        return "", False
    if _looks_like_unsafe_path(raw):
        return "<redacted>", True
    sanitized, sanitized_truncated = _sanitize_activity_text(
        raw, max_chars=MAX_LIVE_PARAMETER_STRING_CHARS
    )
    if not sanitized:
        return None, False
    if sanitized_truncated or len(raw) > MAX_LIVE_PARAMETER_STRING_CHARS:
        return "...", True
    return sanitized, False


def _mapping_from_json_string(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text or len(text) > 4096:
        return value
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return value


def _normalize_live_result_status(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if normalized in {"success", "ok", "completed", "complete"}:
        return "success"
    if normalized in {"empty", "no_result", "none", "not_found"}:
        return "empty"
    if normalized in {"error", "failed", "failure", "denied", "timeout"}:
        return "failed"
    if normalized in {"cancelled", "canceled"}:
        return "cancelled"
    if normalized == "skipped":
        return "skipped"
    return None


def _infer_live_result_status(result: Any) -> str:
    normalized_result = _mapping_from_json_string(result)
    if normalized_result is None or normalized_result == "":
        return "empty"
    if isinstance(normalized_result, Mapping):
        status = _normalize_live_result_status(normalized_result.get("status"))
        if status is not None:
            return status
        if normalized_result.get("error"):
            return "failed"
        count = _infer_live_result_count(normalized_result)
        if count == 0:
            return "empty"
        return "success"
    if isinstance(normalized_result, Sequence) and not isinstance(
        normalized_result, (str, bytes, bytearray)
    ):
        return "success" if len(normalized_result) > 0 else "empty"
    return "success"


def _infer_live_result_count(result: Any) -> int | None:
    normalized_result = _mapping_from_json_string(result)
    if isinstance(normalized_result, Mapping):
        for key in LIVE_RESULT_COUNT_KEYS:
            value = normalized_result.get(key)
            if isinstance(value, int) and value >= 0:
                return value
        for key in LIVE_RESULT_LIST_KEYS:
            value = normalized_result.get(key)
            if isinstance(value, Sequence) and not isinstance(
                value, (str, bytes, bytearray)
            ):
                return len(value)
        return None
    if isinstance(normalized_result, Sequence) and not isinstance(
        normalized_result, (str, bytes, bytearray)
    ):
        return len(normalized_result)
    return None


def _summarize_tool_arguments(args: Any) -> str:
    if isinstance(args, Mapping):
        parts: list[str] = []
        for key in ("relative_path", "path", "file_path"):
            value = args.get(key)
            safe_path = _safe_virtual_path(value)
            if safe_path:
                parts.append(f"{key}={safe_path}")
            elif value is not None:
                parts.append(f"{key}=<redacted>")
        safe_keys = [
            str(key)
            for key in args
            if isinstance(key, str) and not SENSITIVE_KEY_PATTERN.search(key)
        ]
        safe_keys = [key for key in safe_keys if key not in {"relative_path", "path", "file_path"}]
        if safe_keys:
            keys = [
                _sanitize_activity_text(key, max_chars=40)[0]
                for key in sorted(safe_keys)[:5]
            ]
            keys = [key for key in keys if key]
            if keys:
                parts.append("参数键=" + ",".join(keys))
        return "; ".join(parts) if parts else "参数已省略。"
    if args in (None, "", b""):
        return "无参数。"
    return "参数已省略。"


def _summarize_tool_result(result: Any) -> str:
    if isinstance(result, Mapping):
        parts: list[str] = []
        status = _safe_tool_result_status(result)
        if status is not None:
            parts.append(f"status={status}")
        for key in ("relative_path", "path", "virtual_path"):
            safe_path = _safe_virtual_path(result.get(key))
            if safe_path:
                parts.append(f"{key}={safe_path}")
                break
        bytes_count = result.get("bytes")
        if isinstance(bytes_count, int):
            parts.append(f"bytes={bytes_count}")
        sha256 = result.get("sha256")
        if isinstance(sha256, str) and sha256:
            parts.append(f"sha256={sha256[:12]}")
        promoted = result.get("promoted_artifact_id")
        if isinstance(promoted, str) and promoted:
            safe_promoted, _ = _sanitize_activity_text(promoted, max_chars=80)
            if safe_promoted:
                parts.append(f"promoted_artifact_id={safe_promoted}")
        return "; ".join(parts) if parts else "工具返回结构化结果，内容已省略。"
    if isinstance(result, str):
        return f"工具返回文本 {len(result)} 字符，内容已省略。"
    if isinstance(result, Sequence) and not isinstance(result, (str, bytes, bytearray)):
        return f"工具返回 {len(result)} 项，内容已省略。"
    if result is None:
        return "工具未返回内容。"
    return f"工具返回 {type(result).__name__}，内容已省略。"


def _safe_tool_result_status(result: Mapping[str, Any]) -> str | None:
    if result.get("error"):
        return "error"
    status = result.get("status")
    if isinstance(status, str):
        normalized = status.strip().lower()
        if normalized in SAFE_TOOL_RESULT_STATUSES:
            return normalized
        return "reported"
    if status is not None:
        return "reported"
    return None


def _message_value(message: Any, key: str) -> Any:
    if isinstance(message, Mapping):
        return message.get(key)
    return getattr(message, key, None)


def _mapping_or_attr(value: Any, key: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(key)
    return getattr(value, key, None)


def _message_content(message: Any) -> Any:
    return _message_value(message, "content")


def _message_content_text(message: Any) -> str:
    content = _message_content(message)
    if isinstance(content, str):
        return content
    if isinstance(content, Sequence) and not isinstance(content, (str, bytes, bytearray)):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, Mapping) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "".join(parts)
    return ""


def _message_role(message: Any) -> str:
    role = _message_value(message, "role") or _message_value(message, "type")
    if isinstance(role, str):
        return role.lower()
    return type(message).__name__.lower()


def _message_id(message: Any) -> str | None:
    value = _message_value(message, "id")
    return str(value) if value is not None else None


def _message_tool_name(message: Any) -> str:
    name = _message_value(message, "name") or _message_value(message, "tool_name")
    sanitized, _ = _sanitize_activity_text(str(name or "tool"), max_chars=FIELD_LIMITS["tool_name"])
    return sanitized or "tool"


def _tool_message_status(message: Any) -> str:
    status = _message_value(message, "status")
    if isinstance(status, str) and status.lower() in {"error", "failed"}:
        return "failed"
    return "completed"


def _tool_message_live_result_status(message: Any) -> str | None:
    status = _message_value(message, "status")
    if isinstance(status, str):
        normalized = status.strip().lower()
        if normalized in {"error", "failed", "failure", "denied", "timeout"}:
            return "failed"
        if normalized in {"cancelled", "canceled"}:
            return "cancelled"
        if normalized in {"skipped"}:
            return "skipped"
        if normalized in {"success", "ok", "completed", "complete"}:
            return "success"
    return None


def _is_assistant_message(message: Any) -> bool:
    role = _message_role(message)
    class_name = type(message).__name__.lower()
    return role in {"assistant", "ai", "ai_message"} or class_name.startswith("ai")


def _is_tool_message(message: Any) -> bool:
    role = _message_role(message)
    class_name = type(message).__name__.lower()
    return role in {"tool", "tool_message"} or class_name.startswith("tool")


def _is_chunk_message(message: Any) -> bool:
    role = _message_role(message)
    class_name = type(message).__name__.lower()
    return role.endswith("chunk") or class_name.endswith("chunk")


def _looks_like_message(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(key in value for key in ("role", "type", "content", "tool_calls"))
    class_name = type(value).__name__.lower()
    return "message" in class_name or hasattr(value, "content")


def _safe_virtual_path(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    raw = value.strip().replace("\\", "/")
    if not raw:
        return None
    if INTERNAL_PATH_PATTERN.search(raw):
        return None
    if re.match(r"^[A-Za-z]:/", raw) or raw.startswith("//"):
        return None
    if raw.startswith("/"):
        stripped = raw.lstrip("/")
        first = stripped.split("/", 1)[0]
        if first not in SAFE_VIRTUAL_ROOTS:
            return None
        raw = stripped
    parts = [part for part in raw.split("/") if part]
    if any(part in {".", ".."} for part in parts):
        return None
    if parts and parts[0] not in SAFE_VIRTUAL_ROOTS and raw != ".":
        return None
    sanitized, _ = _sanitize_activity_text(raw, max_chars=120)
    return sanitized or None


def _looks_like_unsafe_path(value: str) -> bool:
    raw = value.strip().replace("\\", "/")
    if INTERNAL_PATH_PATTERN.search(raw):
        return True
    if re.match(r"^[A-Za-z]:/", raw) or raw.startswith("//"):
        return True
    if raw.startswith("/"):
        first = raw.lstrip("/").split("/", 1)[0]
        return first not in SAFE_VIRTUAL_ROOTS
    return False


def _sanitize_subgraph_path(values: Iterable[Any]) -> tuple[list[str], bool]:
    path: list[str] = []
    truncated = False
    for value in values:
        if len(path) >= 8:
            truncated = True
            break
        item, item_truncated = _sanitize_activity_text(
            str(value), max_chars=FIELD_LIMITS["subgraph_path"]
        )
        if item:
            path.append(item)
        truncated = truncated or item_truncated
    return path, truncated


def _sanitize_activity_text(value: Any, *, max_chars: int) -> tuple[str, bool]:
    raw = str(value or "").strip()
    if not raw:
        return "", False
    truncated = len(raw) > 8192
    source = raw[:8192]
    text = sanitize_reasoning_text(source, max_chars=8192)
    text = INTERNAL_PATH_PATTERN.sub("<deepagents-internal>", text)
    if len(text) > max_chars:
        text = _trim_text(text, max_chars)
        truncated = True
    return text, truncated


def _trim_text(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 1].rstrip() + "…"


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None
