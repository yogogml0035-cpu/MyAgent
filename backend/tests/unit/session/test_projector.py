from __future__ import annotations

from datetime import datetime, timezone

from app.contracts import SessionEvent
from app.session.projector import ProjectedSessionState, TaskStateProjector


def _make_event(seq: int, event_type: str, **kwargs) -> SessionEvent:
    return SessionEvent(
        id=f"evt-{seq}",
        session_id="sess-1",
        seq=seq,
        type=event_type,
        created_at=datetime.now(timezone.utc),
        message=kwargs.get("message", ""),
        payload=kwargs.get("payload", {}),
        run_id=kwargs.get("run_id"),
    )


class TestTaskStateProjectorInit:
    def test_empty_events_raises(self):
        try:
            TaskStateProjector().project([])
        except ValueError:
            pass
        else:
            raise AssertionError("Expected ValueError for empty events")


class TestTaskStateProjectorBasic:
    def test_task_created_event(self):
        events = [_make_event(0, "task_created", payload={"model": "test-model"})]
        state = TaskStateProjector().project(events)
        assert isinstance(state, ProjectedSessionState)
        assert state.session_id == "sess-1"
        assert state.model == "test-model"
        assert state.status == "idle"

    def test_file_uploaded_increments_count(self):
        events = [
            _make_event(0, "task_created"),
            _make_event(1, "file_uploaded"),
            _make_event(2, "file_uploaded"),
        ]
        state = TaskStateProjector().project(events)
        assert state.upload_count == 2
