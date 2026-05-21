"""Helpers for DeepSeek thinking-mode request payloads."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage
from langchain_openai.chat_models.base import _convert_message_to_dict


def build_deepseek_request_messages(
    messages: Sequence[BaseMessage], *, thinking_enabled: bool
) -> list[dict[str, Any]]:
    """Convert LangChain messages into DeepSeek-compatible request messages."""
    provider_messages: list[dict[str, Any]] = []

    for message in messages:
        provider_message = _convert_message_to_dict(message)
        if _should_include_reasoning_content(
            message,
            provider_message,
            thinking_enabled=thinking_enabled,
        ):
            provider_message["reasoning_content"] = message.additional_kwargs[
                "reasoning_content"
            ]
        else:
            provider_message.pop("reasoning_content", None)
        provider_messages.append(provider_message)

    return provider_messages


def _should_include_reasoning_content(
    message: BaseMessage,
    provider_message: dict[str, Any],
    *,
    thinking_enabled: bool,
) -> bool:
    if not thinking_enabled or not isinstance(message, AIMessage):
        return False
    reasoning_content = message.additional_kwargs.get("reasoning_content")
    return isinstance(reasoning_content, str) and "tool_calls" in provider_message
