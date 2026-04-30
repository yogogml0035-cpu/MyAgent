from __future__ import annotations

import json

from app.contracts import (
    ContextManager,
    NewSessionEvent,
    ToolSpec,
    build_upload_resource_ref,
    resource_ref_payload,
)
from app.harness import DefaultContextManager, context_selection_payload
from app.storage import TaskStorage


def test_default_context_manager_builds_safe_context_without_upload_body_or_paths(tmp_path) -> None:
    storage = TaskStorage(tmp_path / "sessions")
    snapshot = storage.create_session({"model": "deepseek-reasoner"})
    upload_ref = build_upload_resource_ref(
        session_id=snapshot.session_id,
        filename="customer.md",
        size_bytes=120,
        digest="sha256:abc",
        media_type="markdown",
    )
    storage.emit_event(
        snapshot.session_id,
        NewSessionEvent(
            type="file_uploaded",
            message="已上传 customer.md",
            payload={
                "filename": "customer.md",
                "bytes": 120,
                "resource_ref": {
                    **resource_ref_payload(upload_ref),
                    "local_path": str(tmp_path / "sessions" / snapshot.session_id / "uploads"),
                },
                "raw_content": "SECRET_DOC_CANARY_SHOULD_NOT_APPEAR",
            },
        ),
    )
    user_event = storage.emit_event(
        snapshot.session_id,
        NewSessionEvent(
            type="user_message_received",
            message="已接收用户消息，工作流开始执行。",
            payload={"message": "请根据上传资料分析。"},
            run_id="run-1",
        ),
    )
    storage.emit_event(
        snapshot.session_id,
        NewSessionEvent(
            type="tool_result",
            message="工具返回了原始内容。",
            payload={
                "preview": "SECRET_DOC_CANARY_SHOULD_NOT_APPEAR",
                "path": str(tmp_path),
            },
            run_id="run-1",
        ),
    )
    manager = DefaultContextManager(
        [
            ToolSpec(name="web.search", description="Search", input_schema={}, visible_to_model=True),
            ToolSpec(
                name="internal.debug",
                description="Debug",
                input_schema={},
                visible_to_model=False,
            ),
        ]
    )

    context = manager.build_context(
        storage.get_session(snapshot.session_id),
        storage.get_events(snapshot.session_id),
        run_id="run-1",
        policy={"max_messages": 4, "max_message_chars": 20, "token_budget": 2048},
    )
    serialized = json.dumps(context, default=lambda item: getattr(item, "__dict__", str(item)))

    assert isinstance(manager, ContextManager)
    assert context.session_id == snapshot.session_id
    assert context.run_id == "run-1"
    assert context.token_budget == 2048
    assert [tool.name for tool in context.visible_tools] == ["web.search"]
    assert len(context.messages) == 1
    assert context.messages[0].event_id == user_event.id
    assert context.messages[0].content == "请根据上传资料分析。"
    assert context.resource_manifest == (
        {
            "id": f"upload:{snapshot.session_id}:customer.md",
            "kind": "upload",
            "uri": f"myagent://sessions/{snapshot.session_id}/resources/customer.md",
            "name": "customer.md",
            "media_type": "markdown",
            "size_bytes": 120,
            "digest": "sha256:abc",
        },
    )
    assert "SECRET_DOC_CANARY_SHOULD_NOT_APPEAR" not in serialized
    assert str(tmp_path) not in serialized
    assert all(event_ref.type != "file_uploaded" or event_ref.event_id for event_ref in context.event_refs)


def test_default_context_manager_filters_run_scoped_events_and_bounds_messages(tmp_path) -> None:
    storage = TaskStorage(tmp_path / "sessions")
    snapshot = storage.create_session({"model": "deepseek-reasoner"})
    storage.emit_event(
        snapshot.session_id,
        NewSessionEvent(
            type="user_message_received",
            message="old",
            payload={"message": "旧消息"},
            run_id="run-old",
        ),
    )
    storage.emit_event(
        snapshot.session_id,
        NewSessionEvent(
            type="user_message_received",
            message="current",
            payload={"message": "A" * 40},
            run_id="run-current",
        ),
    )
    storage.emit_event(
        snapshot.session_id,
        NewSessionEvent(
            type="assistant_message_created",
            message="assistant",
            payload={"content": "回答内容"},
            run_id="run-current",
        ),
    )

    context = DefaultContextManager().build_context(
        storage.get_session(snapshot.session_id),
        storage.get_events(snapshot.session_id),
        run_id="run-current",
        policy={"max_messages": 1, "max_message_chars": 8, "max_event_refs": 2},
    )

    assert len(context.messages) == 1
    assert context.messages[0].role == "assistant"
    assert context.messages[0].content == "回答内容"
    assert all(event_ref.run_id in {None, "run-current"} for event_ref in context.event_refs)
    assert len(context.event_refs) <= 2


def test_context_selection_payload_uses_ids_only(tmp_path) -> None:
    storage = TaskStorage(tmp_path / "sessions")
    snapshot = storage.create_session({"model": "deepseek-reasoner"})
    upload_ref = build_upload_resource_ref(
        session_id=snapshot.session_id,
        filename="a.md",
        digest="sha256:a",
    )
    storage.emit_event(
        snapshot.session_id,
        NewSessionEvent(
            type="file_uploaded",
            message="已上传 a.md",
            payload={"resource_ref": resource_ref_payload(upload_ref)},
        ),
    )
    context = DefaultContextManager(
        [ToolSpec(name="web.search", description="Search", input_schema={})]
    ).build_context(
        storage.get_session(snapshot.session_id),
        storage.get_events(snapshot.session_id),
        run_id=None,
        policy={"token_budget": 512},
    )

    payload = context_selection_payload(context)

    assert payload["session_id"] == snapshot.session_id
    assert payload["run_id"] is None
    assert payload["resource_refs"] == [f"upload:{snapshot.session_id}:a.md"]
    assert payload["visible_tools"] == ["web.search"]
    assert payload["token_budget"] == 512
    assert all(isinstance(event_id, str) for event_id in payload["event_refs"])


def test_context_contract_accepts_empty_event_list(tmp_path) -> None:
    storage = TaskStorage(tmp_path / "sessions")
    snapshot = storage.create_session({"model": "deepseek-reasoner"})
    context = DefaultContextManager().build_context(
        snapshot,
        [],
        run_id=None,
        policy=None,
    )

    assert context.session_id == snapshot.session_id
    assert context.messages == ()
    assert context.event_refs == ()
