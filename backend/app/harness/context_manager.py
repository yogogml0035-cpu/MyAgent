from __future__ import annotations

from typing import Any

from app.contracts import (
    ContextEventRef,
    ContextManager,
    ContextMessage,
    ContextMessageRole,
    ContextView,
    SessionEvent,
    SessionSnapshot,
    ToolSpec,
)

DEFAULT_MAX_MESSAGES = 8
DEFAULT_MAX_MESSAGE_CHARS = 1200
DEFAULT_MAX_EVENT_REFS = 40
SAFE_RESOURCE_EVENTS = {"file_uploaded"}
SAFE_ARTIFACT_EVENTS = {"run_manifest_created", "task_completed", "deep_agent_completed"}
MESSAGE_EVENTS: dict[str, ContextMessageRole] = {
    "user_message_received": "user",
    "assistant_message_created": "assistant",
}


class DefaultContextManager(ContextManager):
    """Read-only ContextManager skeleton kept out of the production runner."""

    def __init__(self, visible_tools: list[ToolSpec] | None = None) -> None:
        self.visible_tools = tuple(tool for tool in visible_tools or [] if tool.visible_to_model)

    def build_context(
        self,
        session: SessionSnapshot,
        events: list[SessionEvent],
        *,
        run_id: str | None,
        policy: dict[str, Any] | None = None,
    ) -> ContextView:
        context_policy = dict(policy or {})
        max_messages = _positive_int(context_policy.get("max_messages"), DEFAULT_MAX_MESSAGES)
        max_message_chars = _positive_int(
            context_policy.get("max_message_chars"),
            DEFAULT_MAX_MESSAGE_CHARS,
        )
        max_event_refs = _positive_int(
            context_policy.get("max_event_refs"),
            DEFAULT_MAX_EVENT_REFS,
        )
        token_budget = _optional_positive_int(context_policy.get("token_budget"))
        ordered = sorted(events, key=lambda event: event.seq)
        scoped = [
            event
            for event in ordered
            if event.session_id == session.session_id
            and (run_id is None or event.run_id is None or event.run_id == run_id)
        ]
        return ContextView(
            session_id=session.session_id,
            run_id=run_id,
            messages=tuple(_context_messages(scoped, max_messages, max_message_chars)),
            visible_tools=self.visible_tools,
            resource_manifest=tuple(_resource_manifest(scoped)),
            event_refs=tuple(_event_refs(scoped, max_event_refs)),
            token_budget=token_budget,
            policy={
                "max_messages": max_messages,
                "max_message_chars": max_message_chars,
                "max_event_refs": max_event_refs,
            },
        )


def context_selection_payload(view: ContextView) -> dict[str, Any]:
    return {
        "session_id": view.session_id,
        "run_id": view.run_id,
        "event_refs": [event_ref.event_id for event_ref in view.event_refs],
        "resource_refs": [
            str(item.get("id") or item.get("resource_id") or item.get("uri") or "")
            for item in view.resource_manifest
        ],
        "visible_tools": [tool.name for tool in view.visible_tools],
        "token_budget": view.token_budget,
    }


def _context_messages(
    events: list[SessionEvent],
    max_messages: int,
    max_chars: int,
) -> list[ContextMessage]:
    messages: list[ContextMessage] = []
    for event in events:
        role = MESSAGE_EVENTS.get(event.type)
        if role is None:
            continue
        content = _message_content(event)
        if not content:
            continue
        messages.append(
            ContextMessage(
                role=role,
                content=_bounded_text(content, max_chars),
                event_id=event.id,
                run_id=event.run_id,
            )
        )
    return messages[-max_messages:]


def _message_content(event: SessionEvent) -> str:
    raw = event.payload.get("message") or event.payload.get("content")
    if isinstance(raw, str):
        return raw
    return event.message


def _resource_manifest(events: list[SessionEvent]) -> list[dict[str, Any]]:
    resources: dict[str, dict[str, Any]] = {}
    for event in events:
        if event.type in SAFE_RESOURCE_EVENTS:
            resource = _safe_resource_payload(event.payload.get("resource_ref"))
            if resource is not None:
                resources[resource["id"]] = resource
        if event.type in SAFE_ARTIFACT_EVENTS:
            for artifact in _artifact_payloads(event.payload):
                resource = _safe_resource_payload(artifact.get("resource_ref"))
                if resource is not None:
                    resources[resource["id"]] = resource
    return [resources[key] for key in sorted(resources)]


def _artifact_payloads(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_artifacts = payload.get("artifact_refs") or payload.get("artifacts")
    if not isinstance(raw_artifacts, list):
        return []
    return [item for item in raw_artifacts if isinstance(item, dict)]


def _safe_resource_payload(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    resource_id = str(value.get("id") or "").strip()
    uri = str(value.get("uri") or "").strip()
    if not resource_id or not uri.startswith("myagent://"):
        return None
    payload: dict[str, Any] = {
        "id": resource_id,
        "kind": str(value.get("kind") or ""),
        "uri": uri,
    }
    raw_name = value.get("name")
    if isinstance(raw_name, str):
        payload["name"] = raw_name.strip().replace("\\", "/").split("/")[-1]
    raw_media_type = value.get("media_type")
    if isinstance(raw_media_type, str):
        payload["media_type"] = raw_media_type
    raw_size = value.get("size_bytes")
    if isinstance(raw_size, int):
        payload["size_bytes"] = raw_size
    raw_digest = value.get("digest")
    if isinstance(raw_digest, str):
        payload["digest"] = raw_digest
    return payload


def _event_refs(events: list[SessionEvent], max_refs: int) -> list[ContextEventRef]:
    refs = [
        ContextEventRef(
            event_id=event.id,
            type=event.type,
            seq=event.seq,
            run_id=event.run_id,
        )
        for event in events
    ]
    return refs[-max_refs:]


def _bounded_text(value: str, max_chars: int) -> str:
    text = " ".join(value.split())
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "..."


def _positive_int(value: object, default: int) -> int:
    parsed = _optional_positive_int(value)
    return parsed if parsed is not None else default


def _optional_positive_int(value: object) -> int | None:
    if not isinstance(value, (str, bytes, int)):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None
