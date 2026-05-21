from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import SecretStr

from app.models.deepseek_thinking import (
    DeepSeekThinkingChatModel,
    build_deepseek_request_messages,
)


def _thinking_tool_call_messages():
    return [
        HumanMessage(content="请先查询最新招标动态"),
        AIMessage(
            content="我先调用搜索工具确认最新进展。",
            additional_kwargs={"reasoning_content": "需要先拿到最新事实再继续分析。"},
            tool_calls=[
                {
                    "name": "search",
                    "args": {"query": "最新招标动态"},
                    "id": "call-search-1",
                    "type": "tool_call",
                }
            ],
        ),
        ToolMessage(
            content='{"items": ["最新招标动态结果"]}',
            tool_call_id="call-search-1",
        ),
    ]


def test_thinking_messages_preserve_reasoning_content_for_tool_calls():
    payload = build_deepseek_request_messages(
        _thinking_tool_call_messages(),
        thinking_enabled=True,
    )

    assert payload[1] == {
        "role": "assistant",
        "content": "我先调用搜索工具确认最新进展。",
        "reasoning_content": "需要先拿到最新事实再继续分析。",
        "tool_calls": [
            {
                "type": "function",
                "id": "call-search-1",
                "function": {
                    "name": "search",
                    "arguments": '{"query": "最新招标动态"}',
                },
            }
        ],
    }


def test_tool_result_messages_preserve_tool_call_id():
    payload = build_deepseek_request_messages(
        _thinking_tool_call_messages(),
        thinking_enabled=True,
    )

    assert payload[2] == {
        "role": "tool",
        "content": '{"items": ["最新招标动态结果"]}',
        "tool_call_id": "call-search-1",
    }


def test_non_thinking_messages_strip_reasoning_content():
    payload = build_deepseek_request_messages(
        _thinking_tool_call_messages(),
        thinking_enabled=False,
    )

    assert payload[1] == {
        "role": "assistant",
        "content": "我先调用搜索工具确认最新进展。",
        "tool_calls": [
            {
                "type": "function",
                "id": "call-search-1",
                "function": {
                    "name": "search",
                    "arguments": '{"query": "最新招标动态"}',
                },
            }
        ],
    }


def test_thinking_model_payload_preserves_reasoning_content_for_tool_calls():
    model = DeepSeekThinkingChatModel(
        model="deepseek-v4-flash",
        api_key=SecretStr("sk-test"),
        api_base="https://api.deepseek.com",
    )

    payload = model._get_request_payload(_thinking_tool_call_messages())

    assert payload["messages"][1] == {
        "role": "assistant",
        "content": "我先调用搜索工具确认最新进展。",
        "reasoning_content": "需要先拿到最新事实再继续分析。",
        "tool_calls": [
            {
                "type": "function",
                "id": "call-search-1",
                "function": {
                    "name": "search",
                    "arguments": '{"query": "最新招标动态"}',
                },
            }
        ],
    }


def test_adapter_does_not_fabricate_missing_reasoning_content():
    payload = build_deepseek_request_messages(
        [
            HumanMessage(content="请继续"),
            AIMessage(
                content="我先调用搜索工具。",
                tool_calls=[
                    {
                        "name": "search",
                        "args": {"query": "延续上次查询"},
                        "id": "call-search-2",
                        "type": "tool_call",
                    }
                ],
            ),
            ToolMessage(
                content='{"items": ["延续结果"]}',
                tool_call_id="call-search-2",
            ),
        ],
        thinking_enabled=True,
    )

    assert payload[1] == {
        "role": "assistant",
        "content": "我先调用搜索工具。",
        "tool_calls": [
            {
                "type": "function",
                "id": "call-search-2",
                "function": {
                    "name": "search",
                    "arguments": '{"query": "延续上次查询"}',
                },
            }
        ],
    }
