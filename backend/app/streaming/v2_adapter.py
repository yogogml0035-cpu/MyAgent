"""Adapter for LangGraph v2 streaming protocol.

Normalizes raw LangGraph stream events (messages + updates) into a uniform
event dict format consumed by :mod:`app.streaming.event_converter`.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from typing import Any

from langchain_core.messages import AIMessageChunk, ToolMessage
from langgraph.graph.state import CompiledStateGraph

logger = logging.getLogger(__name__)

# Type alias for the normalized event dicts yielded by the adapter.
StreamEvent = dict[str, Any]


async def stream_agent(
    agent: CompiledStateGraph,
    messages: list[Any],
    *,
    config: dict[str, Any] | None = None,
) -> AsyncGenerator[StreamEvent, None]:
    """Stream events from a compiled LangGraph agent.

    Uses ``stream_mode=["messages", "updates"]`` so we receive both
    token-level message chunks and node-level state updates.

    Args:
        agent: A compiled LangGraph ``CompiledStateGraph``.
        messages: LangChain message list (typically ``[HumanMessage(...)]``).
        config: Optional LangGraph runnable config (thread_id, etc.).

    Yields:
        Normalized event dicts with keys ``type`` and ``data``.

    Event types produced:
        - ``message_chunk`` — partial AI text content.
        - ``tool_call`` — tool invocation started.
        - ``tool_result`` — tool execution finished.
        - ``state_update`` — a node completed and emitted state.
    """
    input_payload: dict[str, Any] = {"messages": messages}
    run_config = config or {}

    async for mode, payload in agent.astream(
        input_payload,
        config=run_config,
        stream_mode=["messages", "updates"],
    ):
        if mode == "messages":
            async for event in _handle_messages_mode(payload):
                yield event
        elif mode == "updates":
            async for event in _handle_updates_mode(payload):
                yield event
        else:
            logger.debug("Ignoring unknown stream mode %s", mode)


async def _handle_messages_mode(
    payload: Any,
) -> AsyncGenerator[StreamEvent, None]:
    """Process a ``messages`` stream-mode event.

    ``payload`` is a ``(message_chunk, metadata)`` tuple.
    """
    if not isinstance(payload, tuple) or len(payload) < 2:
        return

    chunk = payload[0]

    # --- Tool results (ToolMessage) ---
    if isinstance(chunk, ToolMessage):
        yield {
            "type": "tool_result",
            "data": {
                "tool_call_id": chunk.tool_call_id,
                "name": chunk.name,
                "content": _extract_text_content(chunk.content),
                "status": chunk.status,
            },
        }
        return

    # --- AI message chunks ---
    if isinstance(chunk, AIMessageChunk):
        # Emit tool_call events when tool_call_chunks are present.
        for tc in chunk.tool_call_chunks:
            if tc.get("name"):
                yield {
                    "type": "tool_call",
                    "data": {
                        "id": tc.get("id"),
                        "name": tc["name"],
                        "args": tc.get("args"),
                    },
                }

        # Emit text content chunks.
        text = _extract_text_content(chunk.content)
        if text:
            yield {
                "type": "message_chunk",
                "data": {
                    "content": text,
                },
            }


async def _handle_updates_mode(
    payload: Any,
) -> AsyncGenerator[StreamEvent, None]:
    """Process an ``updates`` stream-mode event.

    ``payload`` is a dict mapping node names to their output state.
    """
    if not isinstance(payload, dict):
        return

    for node_name, state in payload.items():
        yield {
            "type": "state_update",
            "data": {
                "node": node_name,
                "state_keys": list(state.keys()) if isinstance(state, dict) else [],
            },
        }


def _extract_text_content(content: Any) -> str:
    """Extract plain text from message content that may be a string or list."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "".join(parts)
    return ""
