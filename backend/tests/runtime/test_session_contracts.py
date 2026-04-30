from __future__ import annotations

import json
from datetime import datetime

from app.contracts import NewSessionEvent, SessionEvent, SessionSnapshot, SessionStore
from app.storage import TaskStorage


def test_task_storage_emits_session_events_with_sequence_and_session_id(tmp_path) -> None:
    storage = TaskStorage(tmp_path / "sessions")
    snapshot = storage.create_session({"model": "deepseek-reasoner"})

    emitted = storage.emit_event(
        snapshot.session_id,
        NewSessionEvent(
            type="contract.test",
            message="契约测试事件。",
            payload={"ok": True},
            level="info",
            idempotency_key="contract-test-1",
        ),
    )
    events = storage.get_events(snapshot.session_id)

    assert isinstance(storage, SessionStore)
    assert isinstance(snapshot, SessionSnapshot)
    assert isinstance(emitted, SessionEvent)
    assert [event.seq for event in events] == [1, 2]
    assert {event.session_id for event in events} == {snapshot.session_id}
    assert events[-1].type == "contract.test"
    assert events[-1].payload == {"ok": True}
    assert events[-1].idempotency_key == "contract-test-1"
    assert isinstance(events[-1].created_at, datetime)


def test_task_storage_get_events_filters_after_seq_and_supports_limit(tmp_path) -> None:
    storage = TaskStorage(tmp_path / "sessions")
    snapshot = storage.create_session({"model": "deepseek-reasoner"})
    second = storage.emit_event(
        snapshot.session_id,
        NewSessionEvent(type="second", message="Second", payload={}),
    )
    storage.emit_event(
        snapshot.session_id,
        NewSessionEvent(type="third", message="Third", payload={}),
    )

    assert [event.type for event in storage.get_events(snapshot.session_id, after_seq=second.seq)] == [
        "third"
    ]
    assert [event.type for event in storage.get_events(snapshot.session_id, limit=2)] == [
        "task_created",
        "second",
    ]
    assert [event.type for event in storage.get_events(snapshot.session_id, reverse=True, limit=1)] == [
        "third"
    ]
    assert storage.get_session(snapshot.session_id).latest_seq == 3


def test_legacy_jsonl_events_are_read_with_compatible_sequence(tmp_path) -> None:
    storage = TaskStorage(tmp_path / "sessions")
    state = storage.create_task(None, "deepseek-reasoner")
    events_path = tmp_path / "sessions" / state.task_id / "logs" / "events.jsonl"
    legacy_event = {
        "id": "legacy-event",
        "type": "legacy",
        "message": "Legacy event",
        "created_at": "2026-04-30T00:00:00Z",
        "payload": {"legacy": True},
        "run_id": None,
        "level": None,
    }
    events_path.write_text(json.dumps(legacy_event, ensure_ascii=False) + "\n", encoding="utf-8")

    read_events = storage.read_events(state.task_id)
    session_events = storage.get_events(state.task_id)

    assert read_events[0].session_id == state.task_id
    assert read_events[0].seq == 1
    assert session_events[0].session_id == state.task_id
    assert session_events[0].seq == 1
    assert session_events[0].type == "legacy"
