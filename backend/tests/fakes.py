from __future__ import annotations

import copy
import json
import shutil
import uuid
from pathlib import Path
from typing import Any, Literal

from fastapi import UploadFile

from app.schemas import ChatMessage, EventRecord, TaskRunRecord, TaskState, TaskStatus, TaskSummary
from app.storage import (
    LEGACY_RUN_ID,
    SUPPORTED_UPLOAD_LABEL,
    TYPE_MAP,
    UPLOAD_CHUNK_SIZE,
    UPLOAD_FORMATS,
    UploadConflictError,
    UploadLimitError,
    build_upload_resource_ref,
    document_upload_filename,
    file_sha256,
    generate_run_id,
    normalize_artifact_name,
    resource_ref_payload,
    safe_filename,
    source_format_for_upload,
    summary_title,
    utc_now,
    validate_json_upload,
    validate_run_id,
)


class InMemoryTaskStorage:
    def __init__(self, task_root: Path):
        self.task_root = task_root.resolve()
        self.task_root.mkdir(parents=True, exist_ok=True)
        self.states: dict[str, TaskState] = {}
        self.latest_seq: dict[str, int] = {}

    def initialize(self) -> None:
        return None

    def task_dir(self, task_id: str) -> Path:
        if not task_id or task_id in {".", ".."}:
            raise ValueError("任务 ID 不能为空或相对路径")
        path = (self.task_root / task_id).resolve()
        if self.task_root not in path.parents and path != self.task_root:
            raise ValueError("任务路径超出任务根目录")
        return path

    def create_task(self, message: str | None, model: str) -> TaskState:
        if message is not None:
            raise ValueError("初始消息必须通过运行生命周期接口发送")
        now = utc_now()
        task_id = f"{now.replace(':', '').replace('-', '')}-{uuid.uuid4().hex[:8]}"
        for child in ("uploads", "artifacts", "subagents", "logs"):
            (self.task_dir(task_id) / child).mkdir(parents=True, exist_ok=True)
        self.states[task_id] = TaskState(
            task_id=task_id,
            status="idle",
            model=model,
            created_at=now,
            updated_at=now,
        )
        self.latest_seq[task_id] = 0
        self.append_event(task_id, "task_created", "任务目录已创建。", {"model": model})
        return self.get_task(task_id)

    def get_task(self, task_id: str, *, include_events: bool = True) -> TaskState:
        if task_id not in self.states:
            raise FileNotFoundError(task_id)
        state = copy.deepcopy(self.states[task_id])
        if not include_events:
            state.events = []
        state.upload_count = len(self.list_uploads(task_id))
        state.run_count = len(state.runs)
        state.artifacts = self._artifact_records_for_state(task_id, state)
        return state

    def list_task_summaries(self) -> list[TaskSummary]:
        summaries = []
        for state in self.states.values():
            if not any(message.role == "user" and message.content.strip() for message in state.messages):
                continue
            summaries.append(
                TaskSummary(
                    task_id=state.task_id,
                    title=state.title or summary_title(state.messages),
                    status=state.status,
                    model=state.model,
                    created_at=state.created_at,
                    updated_at=state.updated_at,
                    run_count=len(state.runs),
                    last_message_at=max(
                        (message.created_at for message in state.messages),
                        default=None,
                    ),
                )
            )
        return sorted(summaries, key=lambda item: item.updated_at, reverse=True)

    def rename_task(self, task_id: str, title: str) -> TaskState:
        state = self.states[task_id]
        normalized = " ".join(title.split())
        if not normalized:
            raise ValueError("会话名称不能为空")
        if len(normalized) > 80:
            raise ValueError("会话名称不能超过 80 个字符")
        state.title = normalized
        return self.get_task(task_id, include_events=False)

    def delete_task(self, task_id: str) -> None:
        if task_id not in self.states:
            raise FileNotFoundError(task_id)
        task_path = self.task_dir(task_id)
        del self.states[task_id]
        self.latest_seq.pop(task_id, None)
        shutil.rmtree(task_path, ignore_errors=True)

    def start_run(
        self,
        task_id: str,
        *,
        message: str,
        model: str,
        expected_statuses: set[TaskStatus],
    ) -> tuple[TaskState, str] | None:
        state = self.states[task_id]
        if state.status not in expected_statuses:
            return None
        now = utc_now()
        run_id = generate_run_id()
        self.run_artifact_dir(task_id, run_id).mkdir(parents=True, exist_ok=True)
        state.status = "running"
        state.model = model
        state.error = None
        state.needs_input = None
        state.active_run_id = run_id
        state.updated_at = now
        state.runs.append(
            TaskRunRecord(
                id=run_id,
                status="running",
                message=message,
                model=model,
                started_at=now,
                artifact_base_path=f"artifacts/runs/{run_id}",
            )
        )
        state.messages.append(ChatMessage(role="user", content=message, created_at=now, run_id=run_id))
        return self.get_task(task_id, include_events=False), run_id

    def update_task_if_status(self, task_id: str, expected_statuses: set[TaskStatus], **kwargs):
        return self.update_task_if_status_and_append_events(
            task_id, expected_statuses, events=[], **kwargs
        )

    def update_task_if_status_and_append_event(
        self,
        task_id: str,
        expected_statuses: set[TaskStatus],
        *,
        event_type: str,
        event_message: str,
        event_payload: dict[str, Any] | None = None,
        event_level: Literal["info", "success", "warning", "error"] | None = None,
        **kwargs,
    ):
        return self.update_task_if_status_and_append_events(
            task_id,
            expected_statuses,
            events=[(event_type, event_message, event_payload or {}, event_level)],
            **kwargs,
        )

    def update_task_if_status_and_append_events(
        self,
        task_id: str,
        expected_statuses: set[TaskStatus],
        *,
        events,
        status: TaskStatus | None = None,
        error: str | None = None,
        needs_input: dict[str, Any] | None = None,
        append_message: ChatMessage | None = None,
        run_id: str | None = None,
        artifact_names: list[str] | None = None,
    ):
        state = self.states[task_id]
        if state.status not in expected_statuses:
            return None
        if run_id and state.active_run_id and state.active_run_id != run_id:
            return None
        self._apply_update(
            state,
            status=status,
            error=error,
            needs_input=needs_input,
            append_message=append_message,
            run_id=run_id,
            artifact_names=artifact_names,
        )
        for event_type, message, payload, level in events:
            self.append_event(task_id, event_type, message, payload, run_id=run_id, level=level)
        return self.get_task(task_id)

    def append_event(
        self,
        task_id: str,
        event_type: str,
        message: str,
        payload: dict[str, Any] | None = None,
        *,
        run_id: str | None = None,
        level=None,
    ) -> EventRecord:
        if task_id not in self.states:
            raise FileNotFoundError(task_id)
        self.latest_seq[task_id] = self.latest_seq.get(task_id, 0) + 1
        event = EventRecord(
            id=uuid.uuid4().hex,
            session_id=task_id,
            seq=self.latest_seq[task_id],
            type=event_type,
            message=message,
            created_at=utc_now(),
            payload=payload or {},
            run_id=run_id,
            level=level,
        )
        self.states[task_id].events.append(event)
        return event

    def read_events(self, task_id: str, *, after_id: str | None = None) -> list[EventRecord]:
        events = list(self.states[task_id].events)
        if after_id is None:
            return copy.deepcopy(events)
        for index, event in enumerate(events):
            if event.id == after_id:
                return copy.deepcopy(events[index + 1 :])
        return []

    def list_uploads(self, task_id: str) -> list[Path]:
        upload_dir = self.task_dir(task_id) / "uploads"
        if not upload_dir.exists():
            return []
        return sorted(path for path in upload_dir.iterdir() if path.suffix.lower() in UPLOAD_FORMATS)

    def save_uploads(
        self,
        task_id: str,
        uploads: list[UploadFile],
        *,
        max_files: int,
        max_file_bytes: int,
        max_request_bytes: int,
    ) -> list[Path]:
        if len(self.list_uploads(task_id)) + len(uploads) > max_files:
            raise UploadLimitError(f"最多只能上传 {max_files} 个 {SUPPORTED_UPLOAD_LABEL}")
        upload_dir = self.task_dir(task_id) / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        existing_names = {path.name.casefold() for path in self.list_uploads(task_id)}
        seen_names: set[str] = set()
        batch: list[tuple[UploadFile, str]] = []
        for upload in uploads:
            filename = document_upload_filename(upload.filename or "upload.md")
            key = filename.casefold()
            if key in seen_names:
                raise UploadConflictError(f"本次请求中存在重复上传文件名：{filename}")
            if key in existing_names:
                raise UploadConflictError(f"上传文件已存在：{filename}")
            seen_names.add(key)
            batch.append((upload, filename))

        staged: list[tuple[Path, Path, int]] = []
        total = 0
        try:
            for upload, filename in batch:
                destination = upload_dir / filename
                temp_path = upload_dir / f".{uuid.uuid4().hex}-{filename}.tmp"
                bytes_written = 0
                with temp_path.open("wb") as handle:
                    while True:
                        chunk = upload.file.read(UPLOAD_CHUNK_SIZE)
                        if not chunk:
                            break
                        bytes_written += len(chunk)
                        if bytes_written > max_file_bytes or total + bytes_written > max_request_bytes:
                            raise UploadLimitError("上传文档超过大小限制")
                        handle.write(chunk)
                total += bytes_written
                if source_format_for_upload(destination) == "json":
                    validate_json_upload(temp_path, destination.name)
                staged.append((temp_path, destination, bytes_written))

            for temp_path, destination, _ in staged:
                temp_path.replace(destination)
        except Exception:
            for temp_path, _, _ in staged:
                temp_path.unlink(missing_ok=True)
            for temp_path in upload_dir.glob(".*.tmp"):
                temp_path.unlink(missing_ok=True)
            raise

        saved = [destination for _, destination, _ in staged]
        for _, destination, bytes_written in staged:
            resource_ref = build_upload_resource_ref(
                session_id=task_id,
                filename=destination.name,
                size_bytes=bytes_written,
                digest=file_sha256(destination),
                media_type=source_format_for_upload(destination),
            )
            self.append_event(
                task_id,
                "file_uploaded",
                f"已上传 {destination.name}",
                {
                    "filename": destination.name,
                    "bytes": bytes_written,
                    "resource_id": resource_ref.id,
                    "digest": resource_ref.digest,
                    "uri": resource_ref.uri,
                    "resource_ref": resource_ref_payload(resource_ref),
                },
            )
        return saved

    def interrupt_running_tasks(self, reason: str) -> list[str]:
        interrupted = []
        for task_id, state in list(self.states.items()):
            if state.status == "running":
                self.update_task_if_status_and_append_event(
                    task_id,
                    {"running"},
                    status="interrupted",
                    error=reason,
                    needs_input=None,
                    run_id=state.active_run_id,
                    event_type="task_interrupted",
                    event_message=reason,
                    event_payload={"previous_status": "running"},
                    event_level="warning",
                )
                interrupted.append(task_id)
        return interrupted

    def write_json(self, task_id: str, relative_path: str, data: Any) -> Path:
        return self.write_text(task_id, relative_path, json.dumps(data, ensure_ascii=False, indent=2))

    def write_text(self, task_id: str, relative_path: str, text: str) -> Path:
        path = self._task_relative_path(task_id, relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def write_run_text(self, task_id: str, run_id: str, artifact_name: str, text: str) -> Path:
        name = normalize_artifact_name(artifact_name)
        path = self.run_artifact_dir(task_id, run_id) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        self.record_run_artifact(task_id, run_id, name)
        return path

    def run_artifact_dir(self, task_id: str, run_id: str) -> Path:
        validate_run_id(run_id)
        if run_id == LEGACY_RUN_ID:
            return (self.task_dir(task_id) / "artifacts").resolve()
        return (self.task_dir(task_id) / "artifacts" / "runs" / run_id).resolve()

    def record_run_artifact(self, task_id: str, run_id: str, artifact_name: str, **_kwargs) -> None:
        state = self.states[task_id]
        for run in state.runs:
            if run.id == run_id and artifact_name not in run.artifact_names:
                run.artifact_names.append(artifact_name)
                run.artifact_names.sort()

    def resolve_artifact(self, task_id: str, artifact_name: str) -> Path:
        name = normalize_artifact_name(artifact_name)
        path = self.task_dir(task_id) / "artifacts" / name
        if path.exists():
            return path
        raise FileNotFoundError(name)

    def resolve_run_artifact(self, task_id: str, run_id: str, artifact_name: str) -> Path:
        name = normalize_artifact_name(artifact_name)
        path = self.run_artifact_dir(task_id, run_id) / name
        if path.exists():
            return path
        raise FileNotFoundError(name)

    def _apply_update(
        self,
        state: TaskState,
        *,
        status,
        error,
        needs_input,
        append_message,
        run_id,
        artifact_names,
    ) -> None:
        now = utc_now()
        effective_run_id = run_id or state.active_run_id
        if status:
            state.status = status
        state.error = error
        state.needs_input = needs_input
        state.updated_at = now
        if append_message:
            if effective_run_id and append_message.run_id is None:
                append_message.run_id = effective_run_id
            if not append_message.created_at:
                append_message.created_at = now
            state.messages.append(append_message)
        for run in state.runs:
            if run.id != effective_run_id:
                continue
            if status:
                run.status = status
                if status != "running":
                    run.completed_at = now
                    state.active_run_id = None
            run.error = error
            run.needs_input = needs_input
            if artifact_names:
                merged = set(run.artifact_names)
                merged.update(safe_filename(name) for name in artifact_names)
                run.artifact_names = sorted(merged)

    def _task_relative_path(self, task_id: str, relative_path: str) -> Path:
        path = (self.task_dir(task_id) / relative_path).resolve()
        if self.task_dir(task_id) not in path.parents:
            raise ValueError("任务相对路径超出任务目录")
        return path

    def _artifact_records_for_state(self, task_id: str, state: TaskState):
        records = []
        for run in state.runs:
            for name in run.artifact_names:
                records.append(
                    {
                        "id": f"{run.id}:{name}",
                        "name": name,
                        "type": TYPE_MAP.get(Path(name).suffix.lower(), "text"),
                        "url": f"/api/tasks/{task_id}/runs/{run.id}/artifacts/{name}",
                        "run_id": run.id,
                    }
                )
        return records
