from __future__ import annotations

from datetime import datetime

from app.contracts import NewSessionEvent, SessionEvent
from app.session import TaskStateProjector
from app.storage import TaskStorage


def test_task_state_projector_projects_completed_run_from_session_events(tmp_path) -> None:
    storage = TaskStorage(tmp_path / "sessions")
    snapshot = storage.create_session({"model": "deepseek-reasoner"})
    run_id = "run-projection-complete"
    storage.emit_event(
        snapshot.session_id,
        NewSessionEvent(
            type="user_message_received",
            message="已接收用户消息，工作流开始执行。",
            payload={"message": "你好", "model": "deepseek-reasoner"},
            run_id=run_id,
        ),
    )
    storage.emit_event(
        snapshot.session_id,
        NewSessionEvent(
            type="chat_completed",
            message="简单对话回复已完成。",
            payload={"model": "deepseek-reasoner"},
            run_id=run_id,
        ),
    )

    projection = TaskStateProjector().project(storage.get_events(snapshot.session_id))

    assert projection.session_id == snapshot.session_id
    assert projection.status == "complete"
    assert projection.active_run_id is None
    assert projection.model == "deepseek-reasoner"
    assert projection.run_count == 1
    assert projection.runs[0].id == run_id
    assert projection.runs[0].status == "complete"
    assert projection.runs[0].message == "你好"
    assert projection.user_messages[0]["content"] == "你好"
    assert projection.latest_seq == 3


def test_task_state_projector_projects_uploads_artifacts_and_needs_input(tmp_path) -> None:
    storage = TaskStorage(tmp_path / "sessions")
    snapshot = storage.create_session({"model": "deepseek-reasoner"})
    storage.emit_event(
        snapshot.session_id,
        NewSessionEvent(
            type="file_uploaded",
            message="已上传 tender.md",
            payload={"filename": "tender.md", "bytes": 12},
        ),
    )
    run_event = storage.emit_event(
        snapshot.session_id,
        NewSessionEvent(
            type="user_message_received",
            message="已接收用户消息，工作流开始执行。",
            payload={"message": "分析文件", "model": "deepseek-reasoner"},
            run_id="run-projection",
        ),
    )
    storage.emit_event(
        snapshot.session_id,
        NewSessionEvent(
            type="needs_input",
            message="至少需要上传两份投标人文档才能进行对比。",
            payload={
                "message": "至少需要上传两份投标人文档才能进行对比。",
                "required_file_type": "markdown_or_json",
            },
            run_id=run_event.run_id,
        ),
    )

    projection = TaskStateProjector().project(storage.get_events(snapshot.session_id))

    assert projection.status == "needs_input"
    assert projection.upload_count == 1
    assert projection.active_run_id is None
    assert projection.needs_input is not None
    assert projection.needs_input["required_file_type"] == "markdown_or_json"
    assert projection.runs[0].status == "needs_input"
    assert projection.runs[0].needs_input == projection.needs_input


def test_task_state_projector_projects_failed_run_error(tmp_path) -> None:
    storage = TaskStorage(tmp_path / "sessions")
    snapshot = storage.create_session({"model": "deepseek-reasoner"})
    storage.emit_event(
        snapshot.session_id,
        NewSessionEvent(
            type="user_message_received",
            message="已接收用户消息，工作流开始执行。",
            payload={"message": "执行任务", "model": "deepseek-reasoner"},
            run_id="run-failed",
        ),
    )
    storage.emit_event(
        snapshot.session_id,
        NewSessionEvent(
            type="task_failed",
            message="任务执行失败。",
            payload={"error": "模型服务不可用"},
            run_id="run-failed",
        ),
    )

    projection = TaskStateProjector().project(storage.get_events(snapshot.session_id))

    assert projection.status == "failed"
    assert projection.error == "模型服务不可用"
    assert projection.runs[0].status == "failed"
    assert projection.runs[0].error == "模型服务不可用"


def test_task_state_projector_accepts_legacy_minimal_events() -> None:
    event = SessionEvent(
        id="legacy-1",
        session_id="session-1",
        seq=1,
        type="task_created",
        created_at=datetime.fromisoformat("2026-04-30T00:00:00+00:00"),
        message="任务目录已创建。",
        payload={"model": "deepseek-reasoner"},
    )

    projection = TaskStateProjector().project([event])

    assert projection.session_id == "session-1"
    assert projection.status == "idle"
    assert projection.model == "deepseek-reasoner"
    assert projection.run_count == 0
