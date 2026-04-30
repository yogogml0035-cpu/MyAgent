from __future__ import annotations

from datetime import datetime, timezone

from app.contracts import HarnessEngine, NewSessionEvent, Scheduler, WakeRequest
from app.harness import InlineScheduler, ProjectingHarnessEngine
from app.session import ProjectedSessionState
from app.storage import TaskStorage


def test_projecting_harness_engine_reads_session_events_without_task_runner(tmp_path) -> None:
    storage = TaskStorage(tmp_path / "sessions")
    snapshot = storage.create_session({"model": "deepseek-reasoner"})
    storage.emit_event(
        snapshot.session_id,
        NewSessionEvent(
            type="user_message_received",
            message="已接收用户消息，工作流开始执行。",
            payload={"message": "你好", "model": "deepseek-reasoner"},
            run_id="run-harness",
        ),
    )
    storage.emit_event(
        snapshot.session_id,
        NewSessionEvent(
            type="chat_completed",
            message="简单对话回复已完成。",
            payload={"model": "deepseek-reasoner"},
            run_id="run-harness",
        ),
    )
    engine = ProjectingHarnessEngine(storage)

    projection = engine.run_once(snapshot.session_id, run_id="run-harness")

    assert isinstance(engine, HarnessEngine)
    assert projection.status == "complete"
    assert projection.runs[0].id == "run-harness"
    assert projection.user_messages[0]["content"] == "你好"


def test_inline_scheduler_wakes_engine_and_tracks_running_state() -> None:
    class RecordingEngine(HarnessEngine):
        def __init__(self) -> None:
            self.calls: list[tuple[str, str | None, bool]] = []
            self.scheduler: InlineScheduler | None = None

        def run_once(self, session_id: str, *, run_id: str | None = None) -> ProjectedSessionState:
            assert self.scheduler is not None
            self.calls.append((session_id, run_id, self.scheduler.is_running(session_id)))
            return ProjectedSessionState(
                session_id=session_id,
                status="idle",
                created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                updated_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            )

    engine = RecordingEngine()
    scheduler = InlineScheduler(engine)
    engine.scheduler = scheduler

    projection = scheduler.wake(
        WakeRequest(session_id="session-1", reason="user_message", run_id="run-1")
    )

    assert isinstance(scheduler, Scheduler)
    assert projection.session_id == "session-1"
    assert engine.calls == [("session-1", "run-1", True)]
    assert scheduler.is_running("session-1") is False


def test_inline_scheduler_records_cancel_requests() -> None:
    class IdleEngine(HarnessEngine):
        def run_once(self, session_id: str, *, run_id: str | None = None) -> ProjectedSessionState:
            return ProjectedSessionState(session_id=session_id, status="idle")

    scheduler = InlineScheduler(IdleEngine())

    scheduler.cancel("session-1", run_id="run-1")

    assert scheduler.is_cancel_requested("session-1", "run-1") is True
    assert scheduler.is_cancel_requested("session-1", "run-2") is False
