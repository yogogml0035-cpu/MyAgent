"""Automatic history title generation for task conversations."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.config import Settings
from app.models.provider import create_model

logger = logging.getLogger(__name__)

MAX_AUTO_TITLE_CHARS = 10
TITLE_INPUT_MAX_CHARS = 1200
TITLE_GENERATION_TIMEOUT_SECONDS = 10.0
FALLBACK_TITLE = "新对话"

TITLE_SYSTEM_PROMPT = """你是会话命名助手。
根据用户消息生成一个中文会话名称，要求：
- 10 个字以内
- 概括用户意图或主题
- 不要标点、引号、解释或前后缀
- 不要使用“会话”“标题”等泛词，除非用户消息本身就是这个主题
只输出会话名称。"""

_TITLE_PREFIX_PATTERN = re.compile(
    r"^\s*(?:会话名称|标题|名称|topic|title)\s*[:：\-]\s*",
    re.IGNORECASE,
)
_SURROUNDING_MARKS = " \t\r\n\"'`“”‘’《》<>【】[]()（）{}「」『』"
_TRAILING_PUNCTUATION = "，。！？、；;：:,!?.~…-—_ "


def fallback_title_from_message(message: str) -> str:
    """Build a deterministic title when model generation is unavailable."""
    normalized = " ".join(message.split())
    if not normalized:
        return FALLBACK_TITLE
    return normalized[:MAX_AUTO_TITLE_CHARS]


def sanitize_generated_title(raw_title: Any, source_message: str) -> str:
    """Normalize model output into the stable <=10-character title contract."""
    if isinstance(raw_title, list):
        raw_title = "".join(
            str(item.get("text") if isinstance(item, dict) else item) for item in raw_title
        )
    title = str(raw_title or "").strip()
    title = title.splitlines()[0] if title else ""
    title = _TITLE_PREFIX_PATTERN.sub("", title).strip(_SURROUNDING_MARKS)
    title = title.strip(_TRAILING_PUNCTUATION).strip(_SURROUNDING_MARKS)
    title = " ".join(title.split())
    if not title:
        title = fallback_title_from_message(source_message)
    return title[:MAX_AUTO_TITLE_CHARS] or FALLBACK_TITLE


async def generate_task_title(message: str, model: str, settings: Settings) -> str:
    """Ask the configured chat model for a compact task history title.

    Title generation must never block the task lifecycle from starting. Provider
    failures fall back to a deterministic local title while logging diagnostics
    for backend operators.
    """
    fallback = fallback_title_from_message(message)
    try:
        chat_model = create_model(model, settings=settings, temperature=0.0)
        response = await asyncio.wait_for(
            chat_model.ainvoke(
                [
                    SystemMessage(content=TITLE_SYSTEM_PROMPT),
                    HumanMessage(content=message[:TITLE_INPUT_MAX_CHARS]),
                ]
            ),
            timeout=TITLE_GENERATION_TIMEOUT_SECONDS,
        )
    except Exception as exc:  # pragma: no cover - provider/network failures are environment-specific
        logger.warning("Task title generation failed; using fallback title: %s", exc)
        return fallback
    return sanitize_generated_title(getattr(response, "content", response), message)
