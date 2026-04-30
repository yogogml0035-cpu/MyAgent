from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.contracts import SessionEvent
from app.schemas import TaskStatus

TERMINAL_EVENT_STATUS: dict[str, TaskStatus] = {
    "chat_completed": "complete",
    "search_completed": "complete",
    "deep_agent_completed": "complete",
    "task_completed": "complete",
    "needs_input": "needs_input",
    "task_failed": "failed",
    "task_cancelled": "cancelled",
    "task_interrupted": "interrupted",
}


@dataclass(frozen=True)
class ProjectedRun:
    id: str
    status: TaskStatus
    message: str = ""
    model: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    error: str | None = None
    needs_input: dict[str, Any] | None = None
    artifact_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProjectedSessionState:
    session_id: str
    status: TaskStatus
    created_at: str | None = None
    updated_at: str | None = None
    latest_seq: int = 0
    model: str | None = None
    active_run_id: str | None = None
    run_count: int = 0
    upload_count: int = 0
    user_messages: tuple[dict[str, Any], ...] = ()
    runs: tuple[ProjectedRun, ...] = ()
    error: str | None = None
    needs_input: dict[str, Any] | None = None


@dataclass
class _RunDraft:
    id: str
    status: TaskStatus
    message: str = ""
    model: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    error: str | None = None
    needs_input: dict[str, Any] | None = None
    artifact_names: set[str] = field(default_factory=set)

    def to_projection(self) -> ProjectedRun:
        return ProjectedRun(
            id=self.id,
            status=self.status,
            message=self.message,
            model=self.model,
            started_at=self.started_at,
            completed_at=self.completed_at,
            error=self.error,
            needs_input=self.needs_input,
            artifact_names=tuple(sorted(self.artifact_names)),
        )


class TaskStateProjector:
    def project(self, events: list[SessionEvent]) -> ProjectedSessionState:
        if not events:
            raise ValueError("events 不能为空")

        ordered = sorted(events, key=lambda event: event.seq)
        session_id = ordered[0].session_id
        if any(event.session_id != session_id for event in ordered):
            raise ValueError("events 必须属于同一个 session")

        status: TaskStatus = "idle"
        created_at: str | None = None
        updated_at: str | None = None
        latest_seq = 0
        model: str | None = None
        active_run_id: str | None = None
        upload_count = 0
        user_messages: list[dict[str, Any]] = []
        runs: dict[str, _RunDraft] = {}
        error: str | None = None
        needs_input: dict[str, Any] | None = None

        for event in ordered:
            latest_seq = max(latest_seq, event.seq)
            event_time = event.created_at.isoformat().replace("+00:00", "Z")
            created_at = created_at or event_time
            updated_at = event_time
            if event.type == "task_created":
                model = _optional_text(event.payload.get("model")) or model
                continue
            if event.type == "file_uploaded":
                upload_count += 1
                continue
            if event.type == "user_message_received":
                run = _ensure_run(runs, event, status="running")
                status = "running"
                active_run_id = run.id
                error = None
                needs_input = None
                run.message = _optional_text(event.payload.get("message")) or run.message
                run.model = _optional_text(event.payload.get("model")) or run.model or model
                run.started_at = run.started_at or event_time
                model = run.model or model
                user_messages.append(
                    {
                        "content": run.message,
                        "created_at": event_time,
                        "run_id": event.run_id,
                    }
                )
                continue
            if event.type == "run_manifest_created":
                run = _ensure_run(runs, event, status="running")
                run.started_at = run.started_at or event_time
                continue
            terminal_status = TERMINAL_EVENT_STATUS.get(event.type)
            if terminal_status is not None:
                run = _ensure_run(runs, event, status=terminal_status)
                status = terminal_status
                run.status = terminal_status
                run.completed_at = event_time
                active_run_id = None
                if terminal_status == "failed":
                    error = _optional_text(event.payload.get("error")) or event.message
                    run.error = error
                else:
                    error = None
                    run.error = None
                if terminal_status == "needs_input":
                    needs_input = dict(event.payload)
                    run.needs_input = needs_input
                else:
                    needs_input = None
                    run.needs_input = None
                run.artifact_names.update(_artifact_names_from_event(event))
                continue
            if event.run_id and event.type in {"reasoning_trace", "file_tool_audit"}:
                _ensure_run(runs, event, status="running")

        projected_runs = tuple(run.to_projection() for run in runs.values())
        if status != "running":
            active_run_id = None
        return ProjectedSessionState(
            session_id=session_id,
            status=status,
            created_at=created_at,
            updated_at=updated_at,
            latest_seq=latest_seq,
            model=model,
            active_run_id=active_run_id,
            run_count=len(projected_runs),
            upload_count=upload_count,
            user_messages=tuple(user_messages),
            runs=projected_runs,
            error=error,
            needs_input=needs_input,
        )


def _ensure_run(
    runs: dict[str, _RunDraft], event: SessionEvent, *, status: TaskStatus
) -> _RunDraft:
    run_id = event.run_id or "legacy"
    run = runs.get(run_id)
    if run is None:
        run = _RunDraft(id=run_id, status=status)
        runs[run_id] = run
    return run


def _optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _artifact_names_from_event(event: SessionEvent) -> set[str]:
    names: set[str] = set()
    raw_artifacts = event.payload.get("artifacts")
    if isinstance(raw_artifacts, list):
        names.update(str(name) for name in raw_artifacts if str(name).strip())
    raw_promoted = event.payload.get("promoted_artifacts")
    if isinstance(raw_promoted, list):
        names.update(str(name) for name in raw_promoted if str(name).strip())
    return names
