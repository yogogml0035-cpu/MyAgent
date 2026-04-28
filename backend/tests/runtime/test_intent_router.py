from __future__ import annotations

from typing import Any, cast

import pytest
from pydantic import ValidationError

from app.intent import route_intent
from app.schemas import MessageRequest


@pytest.mark.parametrize(
    ("message", "expected_intent"),
    [
        ("今天天气怎么样？", "weather"),
        ("帮我搜索一下本周建筑行业新闻", "search"),
        ("你好，帮我写一句欢迎语", "chat"),
    ],
)
def test_auto_with_upload_history_keeps_non_document_intents_in_chat(
    message: str, expected_intent: str
) -> None:
    decision = route_intent(message, has_uploads=True)

    assert decision.route in {"chat", "search"}
    assert decision.intent == expected_intent
    assert decision.use_uploads is False
    assert decision.requires_uploads is False
    assert decision.resolved_input_scope == "none"


@pytest.mark.parametrize(
    "message",
    [
        "帮我搜索最新招标公告",
        "搜索投标新闻",
        "查一下今天招标市场新闻",
    ],
)
def test_auto_search_markers_do_not_reuse_uploads_for_document_words(message: str) -> None:
    decision = route_intent(message, has_uploads=True)

    assert decision.route == "search"
    assert decision.intent == "search"
    assert decision.use_uploads is False
    assert decision.resolved_input_scope == "none"


def test_auto_search_with_explicit_file_reference_reuses_uploads() -> None:
    decision = route_intent("搜索刚才这些文件里的投标新闻线索", has_uploads=True)

    assert decision.route == "document_analysis"
    assert decision.intent == "continue_with_uploads"
    assert decision.use_uploads is True
    assert decision.resolved_input_scope == "task_uploads"


@pytest.mark.parametrize(
    ("message", "expected_intent"),
    [
        ("继续分析", "continue_with_uploads"),
        ("根据刚才文件重新总结当前报告", "continue_with_uploads"),
        ("帮我检查是否有串标围标嫌疑", "document_analysis"),
    ],
)
def test_auto_reuses_uploads_for_clear_continue_or_bid_analysis_intents(
    message: str, expected_intent: str
) -> None:
    decision = route_intent(message, has_uploads=True)

    assert decision.route == "document_analysis"
    assert decision.intent == expected_intent
    assert decision.use_uploads is True
    assert decision.requires_uploads is True
    assert decision.resolved_input_scope == "task_uploads"


def test_auto_bid_analysis_without_uploads_requires_document_input() -> None:
    decision = route_intent("帮我检查是否有串标围标嫌疑", has_uploads=False)

    assert decision.route == "document_analysis"
    assert decision.intent == "document_analysis"
    assert decision.use_uploads is False
    assert decision.requires_uploads is True
    assert decision.resolved_input_scope == "none"


def test_explicit_mode_and_input_scope_override_auto_upload_reuse() -> None:
    forced_chat = route_intent(
        "帮我检查是否有串标围标嫌疑",
        mode="chat",
        input_scope="uploads",
        has_uploads=True,
    )
    forced_uploads = route_intent("你好", input_scope="task_uploads", has_uploads=True)
    no_upload_scope = route_intent(
        "帮我检查是否有串标围标嫌疑",
        input_scope="none",
        has_uploads=True,
    )
    forced_bid = route_intent("你好", mode="document_analysis", has_uploads=True)
    forced_search = route_intent("你好", mode="search", input_scope="task_uploads", has_uploads=True)
    forced_deep_agent = route_intent("你好", mode="deep_agent", has_uploads=True)

    assert forced_chat.route == "chat"
    assert forced_chat.use_uploads is False
    assert forced_chat.intent == "forced_chat"
    assert forced_uploads.route == "document_analysis"
    assert forced_uploads.use_uploads is True
    assert forced_uploads.intent == "forced_uploads"
    assert no_upload_scope.route == "chat"
    assert no_upload_scope.use_uploads is False
    assert no_upload_scope.reason == "input_scope_none"
    assert forced_bid.route == "document_analysis"
    assert forced_bid.use_uploads is True
    assert forced_bid.intent == "forced_document_analysis"
    assert forced_search.route == "search"
    assert forced_search.use_uploads is False
    assert forced_deep_agent.route == "deep_agent"
    assert forced_deep_agent.use_uploads is False


def test_message_request_accepts_mode_and_input_scope() -> None:
    request = MessageRequest(message="你好", mode="search", input_scope="task_uploads")

    assert request.mode == "search"
    assert request.input_scope == "task_uploads"


def test_message_request_rejects_unknown_mode_or_input_scope() -> None:
    with pytest.raises(ValidationError):
        MessageRequest.model_validate({"message": "你好", "mode": cast(Any, "invalid")})
    with pytest.raises(ValidationError):
        MessageRequest.model_validate({"message": "你好", "input_scope": cast(Any, "invalid")})
