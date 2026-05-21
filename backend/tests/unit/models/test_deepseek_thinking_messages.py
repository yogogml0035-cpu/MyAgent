from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.models.deepseek_thinking import build_deepseek_request_messages


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
