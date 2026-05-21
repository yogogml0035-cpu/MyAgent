"""Adapter for LangGraph v2 streaming protocol.

Normalizes raw LangGraph stream events (messages + updates) into a uniform
event dict format consumed by :mod:`app.streaming.event_converter`.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator
from typing import Any, Literal, cast

from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph

logger = logging.getLogger(__name__)

# Type alias for the normalized event dicts yielded by the adapter.
StreamEvent = dict[str, Any]
ToolCallAccumulatorKey = tuple[str, str]


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
            return _extract_text_content(msg.content)
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
    tool_call_chunks: dict[ToolCallAccumulatorKey, AIMessageChunk] = {}
    emitted_tool_call_signatures: dict[ToolCallAccumulatorKey, str] = {}

    async for chunk in agent.astream(
        input_payload,
        cast("RunnableConfig", run_config),
        stream_mode=_V2_MODES,
        version="v2",
        subgraphs=True,
    ):
        # LangGraph v2 streaming returns dicts with keys: type, ns, data.
        # Older versions returned (namespace, mode, payload) tuples.
        raw_ns: Any = None
        if isinstance(chunk, dict):
            mode = chunk.get("type")
            payload = chunk.get("data")
            raw_ns = chunk.get("ns")
        elif isinstance(chunk, tuple) and len(chunk) >= 3:
            raw_ns, mode, payload = chunk[0], chunk[1], chunk[2]
        else:
            logger.debug("Skipping unrecognized stream chunk: %s", type(chunk).__name__)
            continue

        # Determine if this event originates from a subgraph (sub-agent).
        is_subgraph = _is_subgraph_namespace(raw_ns)

        if mode == "messages":
            async for event in _handle_messages_mode(
                payload,
                is_subgraph=is_subgraph,
                tool_call_chunks=tool_call_chunks,
                emitted_tool_call_signatures=emitted_tool_call_signatures,
            ):
                yield event
        elif mode == "updates":
            async for event in _handle_updates_mode(payload, is_subgraph=is_subgraph):
                yield event
        elif mode == "values":
            async for event in _handle_values_mode(payload, is_subgraph=is_subgraph):
                yield event
        else:
            logger.debug("Ignoring unknown stream mode %s", mode)


async def _handle_messages_mode(
    payload: Any,
    *,
    is_subgraph: bool = False,
    tool_call_chunks: dict[ToolCallAccumulatorKey, AIMessageChunk] | None = None,
    emitted_tool_call_signatures: dict[ToolCallAccumulatorKey, str] | None = None,
) -> AsyncGenerator[StreamEvent, None]:
    """Process a ``messages`` stream-mode event.

    ``payload`` is a ``(message_chunk, metadata)`` tuple.

    Args:
        is_subgraph: Whether this event originates from a subgraph (sub-agent).
                     Sub-agent text tokens are intermediate output and should NOT
                     be treated as the final answer.
    """
    if not isinstance(payload, tuple) or len(payload) < 2:
        return

    chunk = payload[0]

    accumulators = tool_call_chunks if tool_call_chunks is not None else {}
    emitted_signatures = (
        emitted_tool_call_signatures if emitted_tool_call_signatures is not None else {}
    )

    # --- Tool results (ToolMessage) ---
    if isinstance(chunk, ToolMessage):
        for pending_tool_call_event in _pop_accumulated_tool_call_events(
            chunk.tool_call_id,
            is_subgraph=is_subgraph,
            accumulators=accumulators,
            emitted_signatures=emitted_signatures,
        ):
            yield pending_tool_call_event
        yield {
            "type": "tool_result",
            "data": {
                "tool_call_id": chunk.tool_call_id,
                "name": chunk.name,
                "content": _extract_text_content(chunk.content),
                "status": chunk.status,
                "is_subgraph": is_subgraph,
            },
        }
        return

    # --- AI message chunks ---
    if isinstance(chunk, AIMessageChunk):
        touched_tool_call_keys: list[ToolCallAccumulatorKey] = []

        # Emit tool_call events when tool_call_chunks are present.
        for tc in chunk.tool_call_chunks:
            if isinstance(tc, dict):
                touched_tool_call_keys.append(_tool_call_chunk_key(tc))
            tool_call_event = _accumulate_tool_call_chunk(
                tc,
                is_subgraph=is_subgraph,
                accumulators=accumulators,
                emitted_signatures=emitted_signatures,
            )
            if tool_call_event is not None:
                yield tool_call_event

        reasoning_text = _extract_reasoning_content(chunk)
        if reasoning_text:
            thinking_data: dict[str, Any] = {
                "content": reasoning_text,
                "is_subgraph": is_subgraph,
            }
            thinking_data.update(
                _thinking_tool_call_metadata(
                    chunk,
                    is_subgraph=is_subgraph,
                    accumulators=accumulators,
                    touched_keys=touched_tool_call_keys,
                )
            )
            yield {
                "type": "thinking_chunk",
                "data": thinking_data,
            }

        # Emit text content chunks.
        # Skip text content from sub-agents — those are intermediate output.
        if not is_subgraph:
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
    *,
    is_subgraph: bool = False,
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
                "is_subgraph": is_subgraph,
            },
        }


async def _handle_values_mode(
    payload: Any,
    *,
    is_subgraph: bool = False,
) -> AsyncGenerator[StreamEvent, None]:
    if not isinstance(payload, dict):
        return
    yield {
        "type": "values_snapshot",
        "data": {
            **payload,
            "is_subgraph": is_subgraph,
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


def _accumulate_tool_call_chunk(
    tool_call_chunk: Any,
    *,
    is_subgraph: bool,
    accumulators: dict[ToolCallAccumulatorKey, AIMessageChunk],
    emitted_signatures: dict[ToolCallAccumulatorKey, str],
) -> StreamEvent | None:
    tool_call_chunk_record = dict(tool_call_chunk) if isinstance(tool_call_chunk, dict) else {}
    key = _tool_call_chunk_key(tool_call_chunk_record)
    chunk = AIMessageChunk(content="", tool_call_chunks=cast(Any, [tool_call_chunk_record]))
    accumulated = accumulators.get(key)
    accumulated = accumulated + chunk if accumulated is not None else chunk
    accumulators[key] = accumulated

    event_data = _tool_call_event_data(accumulated, is_subgraph=is_subgraph)
    if event_data is None:
        return None

    signature = _tool_call_event_signature(event_data)
    if emitted_signatures.get(key) == signature:
        return None
    emitted_signatures[key] = signature
    return {"type": "tool_call", "data": event_data}


def _pop_accumulated_tool_call_events(
    tool_call_id: str | None,
    *,
    is_subgraph: bool,
    accumulators: dict[ToolCallAccumulatorKey, AIMessageChunk],
    emitted_signatures: dict[ToolCallAccumulatorKey, str],
) -> list[StreamEvent]:
    if not tool_call_id:
        return []
    events: list[StreamEvent] = []
    for key, accumulated in list(accumulators.items()):
        event_data = _tool_call_event_data(
            accumulated,
            is_subgraph=is_subgraph,
            allow_empty_args=True,
        )
        if event_data is not None and event_data.get("id") == tool_call_id:
            signature = _tool_call_event_signature(event_data)
            if emitted_signatures.get(key) != signature:
                events.append({"type": "tool_call", "data": event_data})
            accumulators.pop(key, None)
            emitted_signatures.pop(key, None)
    return events


def _tool_call_event_signature(event_data: dict[str, Any]) -> str:
    return json.dumps(
        {
            "id": event_data.get("id"),
            "name": event_data.get("name"),
            "args": event_data.get("args"),
            "partial": event_data.get("partial"),
        },
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )


def _tool_call_chunk_key(tool_call_chunk: Any) -> ToolCallAccumulatorKey:
    chunk = dict(tool_call_chunk) if isinstance(tool_call_chunk, dict) else {}
    index = chunk.get("index")
    if isinstance(index, int):
        return ("index", str(index))
    call_id = chunk.get("id")
    if isinstance(call_id, str) and call_id:
        return ("id", call_id)
    name = chunk.get("name")
    if isinstance(name, str) and name:
        return ("name", name)
    return ("index", "0")


def _tool_call_event_data(
    accumulated: AIMessageChunk,
    *,
    is_subgraph: bool,
    allow_empty_args: bool = False,
) -> dict[str, Any] | None:
    chunk = dict(accumulated.tool_call_chunks[0]) if accumulated.tool_call_chunks else {}
    parsed_args, partial = _parse_tool_call_args(chunk.get("args"))
    parsed_call = dict(accumulated.tool_calls[0]) if accumulated.tool_calls else {}
    name = parsed_call.get("name") or chunk.get("name")
    if not isinstance(name, str) or not name:
        return None
    if _is_empty_tool_args_chunk(chunk.get("args")) and not allow_empty_args:
        return None

    index = chunk.get("index")
    call_id = parsed_call.get("id") or chunk.get("id")
    if not call_id and isinstance(index, int):
        call_id = f"tool-index-{index}"
    return {
        "id": call_id,
        "name": name,
        "args": parsed_args,
        "raw_args": chunk.get("args"),
        "partial": partial,
        "is_subgraph": is_subgraph,
    }


def _parse_tool_call_args(raw_args: Any) -> tuple[Any, bool]:
    if isinstance(raw_args, str):
        text = raw_args.strip()
        if not text:
            return {}, False
        try:
            return json.loads(text), False
        except json.JSONDecodeError:
            return text, True
    return raw_args, False


def _is_empty_tool_args_chunk(raw_args: Any) -> bool:
    return isinstance(raw_args, str) and not raw_args.strip()


def _thinking_tool_call_metadata(
    chunk: AIMessageChunk,
    *,
    is_subgraph: bool,
    accumulators: dict[ToolCallAccumulatorKey, AIMessageChunk],
    touched_keys: list[ToolCallAccumulatorKey],
) -> dict[str, Any]:
    tool_calls: list[dict[str, Any]] = []
    seen_keys: set[ToolCallAccumulatorKey] = set()

    for key in touched_keys:
        if key in seen_keys:
            continue
        seen_keys.add(key)
        accumulated = accumulators.get(key)
        if accumulated is None:
            continue
        event_data = _tool_call_event_data(
            accumulated,
            is_subgraph=is_subgraph,
            allow_empty_args=True,
        )
        if event_data is not None:
            tool_calls.append(event_data)

    if not tool_calls:
        tool_calls = _tool_call_metadata_from_parsed_calls(
            getattr(chunk, "tool_calls", None),
            is_subgraph=is_subgraph,
        )

    if not tool_calls:
        return {}

    tool_call_ids = [
        call_id
        for tool_call in tool_calls
        if isinstance((call_id := tool_call.get("id")), str) and call_id
    ]

    metadata: dict[str, Any] = {"tool_calls": tool_calls}
    if tool_call_ids:
        metadata["tool_call_ids"] = tool_call_ids
        if len(tool_call_ids) == 1:
            metadata["tool_call_id"] = tool_call_ids[0]
    return metadata


def _tool_call_metadata_from_parsed_calls(
    raw_tool_calls: Any,
    *,
    is_subgraph: bool,
) -> list[dict[str, Any]]:
    if not isinstance(raw_tool_calls, list):
        return []

    tool_calls: list[dict[str, Any]] = []
    for index, raw_tool_call in enumerate(raw_tool_calls):
        if not isinstance(raw_tool_call, dict):
            continue
        name = raw_tool_call.get("name")
        if not isinstance(name, str) or not name:
            continue
        parsed_args, partial = _parse_tool_call_args(raw_tool_call.get("args"))
        call_id = raw_tool_call.get("id")
        if not isinstance(call_id, str) or not call_id:
            call_id = f"tool-index-{index}"
        tool_calls.append(
            {
                "id": call_id,
                "name": name,
                "args": parsed_args,
                "raw_args": _serialize_tool_call_args(raw_tool_call.get("args")),
                "partial": partial,
                "is_subgraph": is_subgraph,
            }
        )
    return tool_calls


def _serialize_tool_call_args(raw_args: Any) -> Any:
    if isinstance(raw_args, (dict, list)):
        return json.dumps(raw_args, ensure_ascii=False, sort_keys=True)
    return raw_args


def _extract_reasoning_content(chunk: AIMessageChunk) -> str:
    """Extract provider-exposed reasoning text from a message chunk.

    DeepSeek reasoner-compatible providers usually place this stream in
    ``additional_kwargs.reasoning_content``.  A few adapters expose equivalent
    fields or content blocks, so keep the extraction narrow but tolerant.
    """
    additional_kwargs = getattr(chunk, "additional_kwargs", {}) or {}
    response_metadata = getattr(chunk, "response_metadata", {}) or {}
    candidates = [
        additional_kwargs.get("reasoning_content"),
        additional_kwargs.get("reasoning"),
        additional_kwargs.get("thinking"),
        response_metadata.get("reasoning_content"),
    ]

    content = getattr(chunk, "content", None)
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") in {"reasoning", "thinking", "reasoning_content"}:
                candidates.append(block.get("text") or block.get("content"))

    for candidate in candidates:
        text = _extract_text_content(candidate)
        if text:
            return text
    return ""


def _is_subgraph_namespace(raw_ns: Any) -> bool:
    """Return whether a LangGraph v2 namespace points at a subgraph.

    LangGraph can emit namespaces as tuples/lists and namespace entries are not
    guaranteed to be strings. Root graph events use an empty or missing
    namespace; any non-empty namespace is subgraph output.
    """
    if raw_ns is None:
        return False
    if isinstance(raw_ns, str):
        return bool(raw_ns)
    if isinstance(raw_ns, (list, tuple, set, frozenset)):
        return len(raw_ns) > 0
    return bool(raw_ns)
