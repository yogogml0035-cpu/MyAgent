"""Helpers for DeepSeek thinking-mode request payloads."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import AIMessage, BaseMessage
from langchain_deepseek import ChatDeepSeek
from langchain_openai.chat_models.base import (
    _convert_from_v1_to_chat_completions,
    _convert_message_to_dict,
)


class DeepSeekThinkingChatModel(ChatDeepSeek):
    """Preserve reasoning payloads for DeepSeek thinking tool-call turns."""

    def _get_request_payload(
        self,
        input_: LanguageModelInput,
        *,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> dict:
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        if "messages" not in payload:
            return payload

        messages = self._convert_input(input_).to_messages()
        payload["messages"] = build_deepseek_request_messages(
            messages,
            thinking_enabled=True,
        )
        return payload


def build_deepseek_request_messages(
    messages: Sequence[BaseMessage], *, thinking_enabled: bool
) -> list[dict[str, Any]]:
    """Convert LangChain messages into DeepSeek-compatible request messages."""
    provider_messages: list[dict[str, Any]] = []

    for message in messages:
        provider_message = _convert_message_to_dict(
            _convert_from_v1_to_chat_completions(message)
            if isinstance(message, AIMessage)
            else message
        )
        _normalize_deepseek_message_content(provider_message)
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


def _normalize_deepseek_message_content(provider_message: dict[str, Any]) -> None:
    role = provider_message.get("role")
    content = provider_message.get("content")
    if role == "tool" and isinstance(content, list):
        provider_message["content"] = json.dumps(content)
        return

    if role != "assistant" or not isinstance(content, list):
        return

    text_parts = [
        block.get("text", "")
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    ]
    provider_message["content"] = "".join(text_parts) if text_parts else ""


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
