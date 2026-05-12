from __future__ import annotations

import inspect
from collections.abc import AsyncIterator
from typing import Any, cast

import pytest
from langchain_core.messages import AIMessageChunk

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
