from __future__ import annotations

import inspect
from collections.abc import AsyncIterator
from typing import Any, cast

import pytest
from langchain_core.messages import AIMessageChunk, ToolMessage

from app.streaming.v2_adapter import stream_agent


class _FakeStreamingAgent:
    def __init__(self, chunks: list[Any]) -> None:
        self._chunks = chunks

    async def astream(self, *args: Any, **kwargs: Any) -> AsyncIterator[Any]:
        for chunk in self._chunks:
            yield chunk


async def _collect_stream_events(chunks: list[Any]) -> list[dict[str, Any]]:
    agent = _FakeStreamingAgent(chunks)
    return [event async for event in stream_agent(cast(Any, agent), [])]


class TestStreamAgentFunction:
    def test_is_async_generator(self):
        assert inspect.isasyncgenfunction(stream_agent)

    def test_signature_accepts_agent_messages_config(self):
        sig = inspect.signature(stream_agent)
        params = list(sig.parameters)
        assert "agent" in params
        assert "messages" in params
        assert "config" in params


class TestStreamAgentSubgraphFiltering:
    @pytest.mark.asyncio
    async def test_dict_tuple_namespace_message_chunk_is_subgraph(self):
        events = await _collect_stream_events(
            [
                {
                    "type": "messages",
                    "ns": ("researcher", "model"),
                    "data": (AIMessageChunk(content="subgraph token"), {}),
                },
                {
                    "type": "messages",
                    "ns": [],
                    "data": (AIMessageChunk(content="root token"), {}),
                },
            ]
        )

        assert events == [{"type": "message_chunk", "data": {"content": "root token"}}]

    @pytest.mark.asyncio
    async def test_dict_list_namespace_with_non_string_item_is_subgraph(self):
        events = await _collect_stream_events(
            [
                {
                    "type": "messages",
                    "ns": [("researcher", "model")],
                    "data": (AIMessageChunk(content="subgraph token"), {}),
                },
                {
                    "type": "values",
                    "ns": [("researcher", "model")],
                    "data": {"messages": []},
                },
                {
                    "type": "values",
                    "ns": [],
                    "data": {"messages": []},
                },
            ]
        )

        message_chunks = [event for event in events if event["type"] == "message_chunk"]
        snapshots = [event for event in events if event["type"] == "values_snapshot"]

        assert message_chunks == []
        assert [snapshot["data"]["is_subgraph"] for snapshot in snapshots] == [True, False]

    @pytest.mark.asyncio
    async def test_legacy_tuple_namespace_message_chunk_is_subgraph(self):
        events = await _collect_stream_events(
            [
                (("researcher", "model"), "messages", (AIMessageChunk(content="subgraph"), {})),
                ((), "messages", (AIMessageChunk(content="root"), {})),
            ]
        )

        assert events == [{"type": "message_chunk", "data": {"content": "root"}}]

    @pytest.mark.asyncio
    async def test_provider_reasoning_content_emits_thinking_chunk(self):
        events = await _collect_stream_events(
            [
                {
                    "type": "messages",
                    "ns": [],
                    "data": (
                        AIMessageChunk(
                            content="",
                            additional_kwargs={"reasoning_content": "先判断是否需要联网。"},
                        ),
                        {},
                    ),
                },
            ]
        )

        assert events == [
            {
                "type": "thinking_chunk",
                "data": {"content": "先判断是否需要联网。", "is_subgraph": False},
            }
        ]

    @pytest.mark.asyncio
    async def test_tool_call_chunks_are_accumulated_before_tool_result(self):
        events = await _collect_stream_events(
            [
                {
                    "type": "messages",
                    "ns": [],
                    "data": (
                        AIMessageChunk(
                            content="",
                            tool_call_chunks=[
                                {
                                    "name": "searxng_search",
                                    "args": '{"query"',
                                    "id": "call-1",
                                    "index": 0,
                                }
                            ],
                        ),
                        {},
                    ),
                },
                {
                    "type": "messages",
                    "ns": [],
                    "data": (
                        AIMessageChunk(
                            content="",
                            tool_call_chunks=[
                                {
                                    "name": None,
                                    "args": ': "progress log"}',
                                    "id": None,
                                    "index": 0,
                                }
                            ],
                        ),
                        {},
                    ),
                },
            ]
        )

        assert events == [
            {
                "type": "tool_call",
                "data": {
                    "id": "call-1",
                    "name": "searxng_search",
                    "args": '{"query"',
                    "raw_args": '{"query"',
                    "partial": True,
                    "is_subgraph": False,
                },
            },
            {
                "type": "tool_call",
                "data": {
                    "id": "call-1",
                    "name": "searxng_search",
                    "args": {"query": "progress log"},
                    "raw_args": '{"query": "progress log"}',
                    "partial": False,
                    "is_subgraph": False,
                },
            },
        ]

    @pytest.mark.asyncio
    async def test_empty_tool_call_args_chunk_waits_for_final_call_before_result(self):
        events = await _collect_stream_events(
            [
                {
                    "type": "messages",
                    "ns": [],
                    "data": (
                        AIMessageChunk(
                            content="",
                            tool_call_chunks=[
                                {
                                    "name": "list_files",
                                    "args": "",
                                    "id": "call-empty",
                                    "index": 0,
                                }
                            ],
                        ),
                        {},
                    ),
                },
                {
                    "type": "messages",
                    "ns": [],
                    "data": (
                        ToolMessage(
                            content="[]",
                            name="list_files",
                            tool_call_id="call-empty",
                            status="success",
                        ),
                        {},
                    ),
                },
            ]
        )

        assert events == [
            {
                "type": "tool_call",
                "data": {
                    "id": "call-empty",
                    "name": "list_files",
                    "args": {},
                    "raw_args": "",
                    "partial": False,
                    "is_subgraph": False,
                },
            },
            {
                "type": "tool_result",
                "data": {
                    "tool_call_id": "call-empty",
                    "name": "list_files",
                    "content": "[]",
                    "status": "success",
                    "is_subgraph": False,
                },
            },
        ]
