"""Adapter for LangGraph v2 streaming protocol.

Normalizes raw LangGraph stream events (messages + updates) into a uniform
event dict format consumed by :mod:`app.streaming.event_converter`.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from typing import Any, Literal, cast

from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph

logger = logging.getLogger(__name__)

# Type alias for the normalized event dicts yielded by the adapter.
StreamEvent = dict[str, Any]


def extract_final_answer(state: dict[str, Any]) -> str:
    """Extract the final AI answer from a completed graph state.

    Walks ``state["messages"]`` in reverse order and returns the content
    of the last :class:`AIMessage` that has text content and **no**
    ``tool_calls``.  This is the authoritative final answer, as opposed
    to intermediate tool-calling or sub-agent messages.

    Returns an empty string if no suitable message is found.
    """
    messages = state.get("messages", [])
    for msg in reversed(messages):
        if (
            isinstance(msg, AIMessage)
            and getattr(msg, "content", None)
            and not getattr(msg, "tool_calls", None)
        ):
            return msg.content
    return ""


async def stream_agent(
    agent: CompiledStateGraph,
    messages: list[Any],
    *,
    config: dict[str, Any] | None = None,
) -> AsyncGenerator[StreamEvent, None]:
    """Stream events from a compiled LangGraph agent.

    Uses ``stream_mode=["messages", "updates", "values"]`` so we receive
    token-level message chunks, node-level state updates, and the full
    state snapshot after each superstep.

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
        - ``values_snapshot`` — full state snapshot (latest ``values``).
    """
    input_payload: dict[str, Any] = {"messages": messages}
    run_config = config or {}

    _V2_MODES: list[Literal["messages", "updates", "values"]] = [
        "messages",
        "updates",
        "values",
    ]

    async for chunk in agent.astream(
        input_payload,
        cast("RunnableConfig", run_config),
        stream_mode=_V2_MODES,
        version="v2",
    ):
        # LangGraph v2 streaming returns dicts with keys: type, ns, data.
        # Older versions returned (namespace, mode, payload) tuples.
        if isinstance(chunk, dict):
            mode = chunk.get("type")
            payload = chunk.get("data")
        elif isinstance(chunk, tuple) and len(chunk) >= 3:
            _, mode, payload = chunk[0], chunk[1], chunk[2]
        else:
            logger.debug("Skipping unrecognized stream chunk: %s", type(chunk).__name__)
            continue

        if mode == "messages":
            async for event in _handle_messages_mode(payload):
                yield event
        elif mode == "updates":
            async for event in _handle_updates_mode(payload):
                yield event
        elif mode == "values":
            async for event in _handle_values_mode(payload):
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


async def _handle_values_mode(
    payload: Any,
) -> AsyncGenerator[StreamEvent, None]:
    if not isinstance(payload, dict):
        return
    yield {
        "type": "values_snapshot",
        "data": payload,
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
