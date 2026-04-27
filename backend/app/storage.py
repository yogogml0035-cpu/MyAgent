from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import datetime, timezone
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Literal, TypeAlias

from fastapi import UploadFile

from .schemas import ArtifactRecord, ChatMessage, EventRecord, TaskState, TaskStatus

ArtifactType: TypeAlias = Literal["html", "markdown", "json", "text"]
UPLOAD_CHUNK_SIZE = 1024 * 1024
MAX_FILENAME_BYTES = 180


class UploadConflictError(ValueError):
    pass


class UploadLimitError(ValueError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def safe_filename(name: str) -> str:
    normalized = sanitize_filename(name)
    return trim_filename_bytes(normalized or "upload.md", MAX_FILENAME_BYTES)


def sanitize_filename(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._\-\u4e00-\u9fff]+", "_", name).strip("._")


def trim_filename_bytes(filename: str, max_bytes: int) -> str:
    if len(filename.encode("utf-8")) <= max_bytes:
        return filename
    suffix = Path(filename).suffix
    suffix_bytes = len(suffix.encode("utf-8"))
    if suffix_bytes >= max_bytes:
        suffix = ""
        suffix_bytes = 0
    budget = max_bytes - suffix_bytes
    stem = filename[: -len(suffix)] if suffix else filename
    encoded = stem.encode("utf-8")[:budget]
    trimmed_stem = encoded.decode("utf-8", errors="ignore").strip("._")
    return f"{trimmed_stem or 'upload'}{suffix}"


def markdown_upload_filename(name: str) -> str:
    filename = sanitize_filename(name or "upload.md") or "upload.md"
    if not filename.lower().endswith(".md"):
        raise ValueError("Only Markdown files are supported in v1")
    if len(filename.encode("utf-8")) > MAX_FILENAME_BYTES:
        raise ValueError(f"Upload filename exceeds the {MAX_FILENAME_BYTES} byte limit")
    return f"{filename[:-3]}.md"


class TaskStorage:
    def __init__(self, task_root: Path):
        self.task_root = task_root.resolve()
        self.task_root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def task_dir(self, task_id: str) -> Path:
        path = (self.task_root / task_id).resolve()
        if self.task_root not in path.parents and path != self.task_root:
            raise ValueError("Task path escaped task root")
        return path

    def create_task(self, message: str | None, model: str) -> TaskState:
        now = utc_now()
        task_id = f"{now.replace(':', '').replace('-', '')}-{uuid.uuid4().hex[:8]}"
        task_dir = self.task_dir(task_id)
        for child in ("uploads", "artifacts", "subagents", "logs"):
            (task_dir / child).mkdir(parents=True, exist_ok=True)
        state = TaskState(
            task_id=task_id,
            status="idle",
            model=model,
            created_at=now,
            updated_at=now,
        )
        if message:
            state.messages.append(ChatMessage(role="user", content=message, created_at=now))
        self._write_state(state)
        self.append_event(task_id, "task_created", "Task directory created", {"model": model})
        return self.get_task(task_id)

    def get_task(self, task_id: str, *, include_events: bool = True) -> TaskState:
        with self._lock:
            state_path = self.task_dir(task_id) / "state.json"
            data = json.loads(state_path.read_text(encoding="utf-8"))
            data["events"] = (
                [event.model_dump() for event in self.read_events(task_id)]
                if include_events
                else []
            )
            data["artifacts"] = [artifact.model_dump() for artifact in self.list_artifacts(task_id)]
            data["upload_count"] = len(self.list_uploads(task_id))
            return TaskState(**data)

    def update_task(
        self,
        task_id: str,
        *,
        status: TaskStatus | None = None,
        error: str | None = None,
        needs_input: dict[str, Any] | None = None,
        append_message: ChatMessage | None = None,
    ) -> TaskState:
        with self._lock:
            state = self._read_state(task_id)
            if status:
                state.status = status
            state.error = error
            state.needs_input = needs_input
            state.updated_at = utc_now()
            if append_message:
                state.messages.append(append_message)
            self._write_state(state)
            return self.get_task(task_id)

    def update_task_if_status(
        self,
        task_id: str,
        expected_statuses: set[TaskStatus],
        *,
        status: TaskStatus | None = None,
        error: str | None = None,
        needs_input: dict[str, Any] | None = None,
        append_message: ChatMessage | None = None,
    ) -> TaskState | None:
        with self._lock:
            state = self._read_state(task_id)
            if state.status not in expected_statuses:
                return None
            if status:
                state.status = status
            state.error = error
            state.needs_input = needs_input
            state.updated_at = utc_now()
            if append_message:
                state.messages.append(append_message)
            self._write_state(state)
            return self.get_task(task_id)

    def save_uploads(
        self,
        task_id: str,
        uploads: list[UploadFile],
        *,
        max_files: int,
        max_file_bytes: int,
        max_request_bytes: int,
    ) -> list[Path]:
        with self._lock:
            upload_dir = self.task_dir(task_id) / "uploads"
            if len(self.list_uploads(task_id)) + len(uploads) > max_files:
                raise UploadLimitError(f"At most {max_files} Markdown files can be uploaded")

            batch = self._validate_upload_batch(task_id, uploads)
            staged: list[tuple[Path, Path, int]] = []
            total_bytes_written = 0
            try:
                for upload, filename in batch:
                    destination = upload_dir / filename
                    temp_path = upload_dir / f".{uuid.uuid4().hex}-{filename}.tmp"
                    try:
                        bytes_written = self._write_limited_upload(
                            upload,
                            temp_path,
                            max_file_bytes=max_file_bytes,
                            max_request_bytes=max_request_bytes,
                            current_request_bytes=total_bytes_written,
                        )
                    except Exception:
                        temp_path.unlink(missing_ok=True)
                        raise
                    total_bytes_written += bytes_written
                    staged.append((temp_path, destination, bytes_written))
                for temp_path, destination, _ in staged:
                    temp_path.replace(destination)
            except Exception:
                for temp_path, _, _ in staged:
                    temp_path.unlink(missing_ok=True)
                raise

            saved_paths = [destination for _, destination, _ in staged]
            for _, destination, bytes_written in staged:
                self.append_event(
                    task_id,
                    "file_uploaded",
                    f"Uploaded {destination.name}",
                    {"filename": destination.name, "bytes": bytes_written},
                )
            return saved_paths

    def list_uploads(self, task_id: str) -> list[Path]:
        upload_dir = self.task_dir(task_id) / "uploads"
        if not upload_dir.exists():
            return []
        return sorted(
            path for path in upload_dir.iterdir() if path.is_file() and path.suffix.lower() == ".md"
        )

    def _validate_upload_batch(
        self, task_id: str, uploads: list[UploadFile]
    ) -> list[tuple[UploadFile, str]]:
        existing_names = {path.name.casefold() for path in self.list_uploads(task_id)}
        seen_names: set[str] = set()
        batch: list[tuple[UploadFile, str]] = []
        for upload in uploads:
            filename = markdown_upload_filename(upload.filename or "upload.md")
            key = filename.casefold()
            if key in seen_names:
                raise UploadConflictError(f"Duplicate upload filename in request: {filename}")
            if key in existing_names:
                raise UploadConflictError(f"Upload already exists: {filename}")
            seen_names.add(key)
            batch.append((upload, filename))
        return batch

    @staticmethod
    def _write_limited_upload(
        upload: UploadFile,
        destination: Path,
        *,
        max_file_bytes: int,
        max_request_bytes: int,
        current_request_bytes: int,
    ) -> int:
        bytes_written = 0
        with destination.open("wb") as handle:
            while True:
                chunk = upload.file.read(UPLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                bytes_written += len(chunk)
                if bytes_written > max_file_bytes:
                    raise UploadLimitError(
                        f"Markdown file exceeds the {max_file_bytes} byte upload limit"
                    )
                if current_request_bytes + bytes_written > max_request_bytes:
                    raise UploadLimitError(
                        f"Upload request exceeds the {max_request_bytes} byte limit"
                    )
                handle.write(chunk)
        return bytes_written

    def append_event(
        self, task_id: str, event_type: str, message: str, payload: dict[str, Any] | None = None
    ) -> EventRecord:
        with self._lock:
            event = EventRecord(
                id=uuid.uuid4().hex,
                type=event_type,
                message=message,
                created_at=utc_now(),
                payload=payload or {},
            )
            events_path = self.task_dir(task_id) / "logs" / "events.jsonl"
            with events_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event.model_dump(), ensure_ascii=False) + "\n")
            return event

    def read_events(self, task_id: str, *, after_id: str | None = None) -> list[EventRecord]:
        with self._lock:
            events_path = self.task_dir(task_id) / "logs" / "events.jsonl"
            if not events_path.exists():
                return []
            lines = events_path.read_text(encoding="utf-8").splitlines()
            events: list[EventRecord] = []
            include = after_id is None
            for index, line in enumerate(lines):
                if not line.strip():
                    continue
                try:
                    event = EventRecord(**json.loads(line))
                except JSONDecodeError:
                    if index == len(lines) - 1:
                        break
                    raise
                if include:
                    events.append(event)
                elif event.id == after_id:
                    include = True
            return events

    def list_task_ids(self) -> list[str]:
        with self._lock:
            return sorted(
                path.name
                for path in self.task_root.iterdir()
                if path.is_dir() and (path / "state.json").exists()
            )

    def interrupt_running_tasks(self, reason: str) -> list[str]:
        interrupted = []
        with self._lock:
            for task_id in self.list_task_ids():
                if self.mark_interrupted_if_running(task_id, reason):
                    interrupted.append(task_id)
        return interrupted

    def mark_interrupted_if_running(self, task_id: str, reason: str) -> bool:
        with self._lock:
            state = self._read_state(task_id)
            if state.status != "running":
                return False
            state.status = "interrupted"
            state.error = reason
            state.needs_input = None
            state.updated_at = utc_now()
            self._write_state(state)
            self.append_event(
                task_id,
                "task_interrupted",
                reason,
                {"previous_status": "running"},
            )
            return True

    def write_json(self, task_id: str, relative_path: str, data: Any) -> Path:
        path = self.task_dir(task_id) / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def write_text(self, task_id: str, relative_path: str, text: str) -> Path:
        path = self.task_dir(task_id) / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def list_artifacts(self, task_id: str) -> list[ArtifactRecord]:
        artifact_dir = self.task_dir(task_id) / "artifacts"
        records: list[ArtifactRecord] = []
        if not artifact_dir.exists():
            return records
        type_map: dict[str, ArtifactType] = {
            ".html": "html",
            ".md": "markdown",
            ".json": "json",
            ".txt": "text",
        }
        for path in sorted(artifact_dir.iterdir()):
            if path.is_file():
                records.append(
                    ArtifactRecord(
                        name=path.name,
                        type=type_map.get(path.suffix.lower(), "text"),
                        url=f"/api/tasks/{task_id}/artifacts/{path.name}",
                    )
                )
        return records

    def resolve_artifact(self, task_id: str, artifact_name: str) -> Path:
        safe_name = safe_filename(artifact_name)
        path = (self.task_dir(task_id) / "artifacts" / safe_name).resolve()
        artifact_root = (self.task_dir(task_id) / "artifacts").resolve()
        if artifact_root not in path.parents:
            raise ValueError("Artifact path escaped task root")
        return path

    def _read_state(self, task_id: str) -> TaskState:
        data = json.loads((self.task_dir(task_id) / "state.json").read_text(encoding="utf-8"))
        data.pop("events", None)
        data.pop("artifacts", None)
        return TaskState(**data)

    def _write_state(self, state: TaskState) -> None:
        data = state.model_dump()
        data["events"] = []
        data["artifacts"] = []
        path = self.task_dir(state.task_id) / "state.json"
        temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        temp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(path)
