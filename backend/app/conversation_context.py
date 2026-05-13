from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from app.config import Settings
from app.schemas import ChatMessage
from app.security.scanner import redact_sensitive_text, scan_text_for_secrets


@dataclass(frozen=True)
class ConversationContext:
    messages: list[BaseMessage]
    summary: str | None = None
    recent_message_count: int = 0
    cached_tool_results: list[str] = field(default_factory=list)

    @property
    def loaded(self) -> bool:
        return bool(self.summary or self.recent_message_count or self.cached_tool_results)

    def event_payload(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "summary_present": bool(self.summary),
            "recent_message_count": self.recent_message_count,
            "cached_tool_result_count": len(self.cached_tool_results),
            "summary_preview": _clip(self.summary or "", 280),
            "cached_tool_previews": [_clip(item, 180) for item in self.cached_tool_results[:3]],
            "live": {
                "schema_version": 1,
                "kind": "status",
                "stage": "organizing_state",
                "display_text": "已载入会话上下文",
                "diagnostic_label": "conversation_context",
                "parameter_items": [
                    {"key": "最近消息", "value": self.recent_message_count},
                    {"key": "摘要", "value": bool(self.summary)},
                    {"key": "缓存", "value": len(self.cached_tool_results)},
                ],
            },
        }


class ConversationStorage(Protocol):
    def get_task_messages(self, task_id: str) -> list[ChatMessage]: ...

    def get_context_summary(self, task_id: str) -> str | None: ...

    def upsert_context_summary(
        self, task_id: str, summary: str, *, covered_message_count: int
    ) -> None: ...

    def list_fresh_tool_cache(
        self, task_id: str, *, limit: int = 5
    ) -> Sequence[object]: ...


class ConversationContextBuilder:
    """Build deterministic per-session context before every model call."""

    def __init__(self, settings: Settings, storage: ConversationStorage) -> None:
        self.settings = settings
        self.storage = storage

    def build(self, *, task_id: str, current_message: str) -> ConversationContext:
        messages = self.storage.get_task_messages(task_id)
        previous_messages = _without_current_tail(messages, current_message)
        cached_tools = (
            []
            if _asks_for_fresh_context(current_message)
            else self.storage.list_fresh_tool_cache(task_id, limit=5)
        )
        cached_tool_previews = [_tool_cache_preview(item) for item in cached_tools]
        summary = self.storage.get_context_summary(task_id)
        if summary is None and len(previous_messages) > self.settings.recent_message_limit:
            summary = build_deterministic_summary(
                previous_messages[: -self.settings.recent_message_limit]
            )
            if summary:
                self.storage.upsert_context_summary(
                    task_id,
                    summary,
                    covered_message_count=max(
                        0, len(previous_messages) - self.settings.recent_message_limit
                    ),
                )

        recent_messages = previous_messages[-self.settings.recent_message_limit :]
        context_messages: list[BaseMessage] = []
        system_parts = [
            "以下是同一 MyAgent 会话的确定性上下文。它来自平台侧 Postgres session 记录，"
            "用于保持本会话连续性；若与本轮用户输入冲突，以本轮用户输入为准。"
        ]
        if summary:
            system_parts.append(f"会话摘要：{_sanitize(summary, 1200)}")
        if recent_messages:
            system_parts.append("最近消息已按原角色附在后续消息中。")
        if cached_tools:
            system_parts.append("以下是 10 分钟内同一会话的工具缓存，适合先回答已知内容；若用户明确要求刷新、最新或现在信息，必须重新调用实时工具。")
            system_parts.extend(_tool_cache_context(item) for item in cached_tools)
        context_messages.append(SystemMessage(content="\n".join(system_parts)))
        context_messages.extend(_to_langchain_messages(recent_messages))
        return ConversationContext(
            messages=context_messages,
            summary=summary,
            recent_message_count=len(recent_messages),
            cached_tool_results=[preview for preview in cached_tool_previews if preview],
        )


def build_deterministic_summary(messages: list[ChatMessage]) -> str:
    lines: list[str] = []
    for message in messages[-20:]:
        content = _sanitize(message.content, 180)
        if not content:
            continue
        role = "用户" if message.role == "user" else "AI" if message.role == "assistant" else "系统"
        lines.append(f"{role}: {content}")
    if not lines:
        return ""
    return "；".join(lines)[-1800:]


def _without_current_tail(messages: list[ChatMessage], current_message: str) -> list[ChatMessage]:
    if not messages:
        return []
    tail = messages[-1]
    if tail.role == "user" and tail.content == current_message:
        return messages[:-1]
    return messages


def _to_langchain_messages(messages: list[ChatMessage]) -> list[BaseMessage]:
    result: list[BaseMessage] = []
    for message in messages:
        content = _sanitize(message.content, 4000)
        if not content:
            continue
        if message.role == "user":
            result.append(HumanMessage(content=content))
        elif message.role == "assistant":
            result.append(AIMessage(content=content))
        else:
            result.append(SystemMessage(content=content))
    return result


def _sanitize(text: str, max_chars: int) -> str:
    redacted = redact_sensitive_text(text)
    if scan_text_for_secrets(redacted, source="conversation_context"):
        return "[已移除敏感内容]"
    return _clip(" ".join(redacted.split()), max_chars)


def _clip(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 3)].rstrip() + "..."


def _tool_cache_preview(item: object) -> str:
    tool_name = str(getattr(item, "tool_name", "") or "tool")
    query = _sanitize(str(getattr(item, "query", "") or ""), 120)
    created_at = str(getattr(item, "created_at", "") or "")
    if not query:
        return ""
    return _clip(f"{tool_name}: {query}（{created_at}）", 180)


def _tool_cache_context(item: object) -> str:
    tool_name = str(getattr(item, "tool_name", "") or "tool")
    query = _sanitize(str(getattr(item, "query", "") or ""), 180)
    result = _sanitize(str(getattr(item, "result_text", "") or ""), 1200)
    if not query or not result:
        return ""
    return f"- {tool_name} / {query}: {result}"


def _asks_for_fresh_context(message: str) -> bool:
    normalized = message.lower()
    markers = (
        "刷新",
        "重新查",
        "再查",
        "最新",
        "现在",
        "实时",
        "today",
        "latest",
        "refresh",
        "current",
        "now",
    )
    return any(marker in normalized for marker in markers)
