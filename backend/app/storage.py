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

from .schemas import (
    ArtifactRecord,
    ChatMessage,
    EventRecord,
    TaskRunRecord,
    TaskState,
    TaskStatus,
    TaskSummary,
)

ArtifactType: TypeAlias = Literal["html", "markdown", "json", "text"]
UploadSourceFormat: TypeAlias = Literal["markdown", "json"]
UPLOAD_CHUNK_SIZE = 1024 * 1024
MAX_FILENAME_BYTES = 180
LEGACY_RUN_ID = "legacy"
RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")
RUN_ARTIFACT_NAMES = {
    "input-manifest.json",
    "task-plan.md",
    "evidence.json",
    "final-summary.md",
    "report.html",
}
TYPE_MAP: dict[str, ArtifactType] = {
    ".html": "html",
    ".md": "markdown",
    ".json": "json",
    ".txt": "text",
}
UPLOAD_FORMATS: dict[str, UploadSourceFormat] = {
    ".md": "markdown",
    ".json": "json",
}


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


def document_upload_filename(name: str) -> str:
    filename = sanitize_filename(name or "upload.md") or "upload.md"
    suffix = Path(filename).suffix
    normalized_suffix = suffix.lower()
    if normalized_suffix not in UPLOAD_FORMATS:
        raise ValueError("仅支持上传 Markdown 或 JSON 文件")
    normalized_name = f"{filename[: -len(suffix)]}{normalized_suffix}"
    if len(normalized_name.encode("utf-8")) > MAX_FILENAME_BYTES:
        raise ValueError(f"上传文件名超过 {MAX_FILENAME_BYTES} 字节限制")
    return normalized_name


def source_format_for_upload(path: Path) -> UploadSourceFormat:
    suffix = path.suffix.lower()
    try:
        return UPLOAD_FORMATS[suffix]
    except KeyError:
        raise ValueError("不支持的上传文件类型") from None


def validate_json_upload(path: Path, filename: str) -> None:
    try:
        json.loads(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError as exc:
        raise ValueError(f"JSON 文件 {filename} 无效：文件必须使用 UTF-8 编码") from exc
    except JSONDecodeError as exc:
        raise ValueError(f"JSON 文件 {filename} 无效：内容不是合法 JSON") from exc


def generate_run_id() -> str:
    stamp = utc_now().replace(":", "").replace("-", "").replace("Z", "")
    return f"run-{stamp}-{uuid.uuid4().hex[:8]}"


def normalize_artifact_name(artifact_name: str) -> str:
    if not artifact_name or artifact_name in {".", ".."}:
        raise ValueError("产物名称无效")
    if Path(artifact_name).name != artifact_name:
        raise ValueError("产物名称不能包含路径分隔符")
    normalized = safe_filename(artifact_name)
    if normalized != artifact_name:
        raise ValueError("产物名称无效")
    return normalized


def validate_run_id(run_id: str) -> str:
    if not run_id or not RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError("运行 ID 无效")
    return run_id


def summary_title(messages: list[ChatMessage]) -> str:
    for message in messages:
        if message.role != "user":
            continue
        visible = " ".join(message.content.split())
        if visible:
            return visible[:5]
    return "新对话"


class TaskStorage:
    def __init__(self, task_root: Path):
        self.task_root = task_root.resolve()
        self.task_root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def task_dir(self, task_id: str) -> Path:
        path = (self.task_root / task_id).resolve()
        if self.task_root not in path.parents and path != self.task_root:
            raise ValueError("任务路径超出任务根目录")
        return path

    def create_task(self, message: str | None, model: str) -> TaskState:
        if message is not None:
            raise ValueError("初始消息必须通过运行生命周期接口发送")
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
        self._write_state(state)
        self.append_event(task_id, "task_created", "任务目录已创建。", {"model": model})
        return self.get_task(task_id)

    def get_task(self, task_id: str, *, include_events: bool = True) -> TaskState:
        with self._lock:
            state = self._read_state(task_id, synthesize_legacy=True)
            state.events = self.read_events(task_id) if include_events else []
            state.artifacts = self._artifact_records_for_state(task_id, state)
            state.upload_count = len(self.list_uploads(task_id))
            state.run_count = len(state.runs)
            return state

    def list_task_summaries(self) -> list[TaskSummary]:
        with self._lock:
            summaries: list[TaskSummary] = []
            for state in (
                self.get_task(task_id, include_events=False) for task_id in self.list_task_ids()
            ):
                has_user_message = any(
                    message.role == "user" and message.content.strip()
                    for message in state.messages
                )
                if not has_user_message:
                    continue
                summaries.append(
                    TaskSummary(
                        task_id=state.task_id,
                        title=summary_title(state.messages),
                        status=state.status,
                        model=state.model,
                        created_at=state.created_at,
                        updated_at=state.updated_at,
                        run_count=len(state.runs),
                        last_message_at=max(
                            (message.created_at for message in state.messages),
                            default=None,
                        ),
                    ),
                )
            return sorted(
                summaries,
                key=lambda item: (item.updated_at, item.created_at, item.task_id),
                reverse=True,
            )

    def update_task(
        self,
        task_id: str,
        *,
        status: TaskStatus | None = None,
        error: str | None = None,
        needs_input: dict[str, Any] | None = None,
        append_message: ChatMessage | None = None,
        run_id: str | None = None,
        artifact_names: list[str] | None = None,
    ) -> TaskState:
        with self._lock:
            state = self._read_state(task_id, synthesize_legacy=True)
            self._apply_task_update(
                state,
                status=status,
                error=error,
                needs_input=needs_input,
                append_message=append_message,
                run_id=run_id,
                artifact_names=artifact_names,
            )
            self._write_state(state)
            return self.get_task(task_id)

    def start_run(
        self,
        task_id: str,
        *,
        message: str,
        model: str,
        expected_statuses: set[TaskStatus],
    ) -> tuple[TaskState, str] | None:
        with self._lock:
            state = self._read_state(task_id, synthesize_legacy=True)
            if state.status not in expected_statuses:
                return None
            now = utc_now()
            run_id = generate_run_id()
            run_dir = self.run_artifact_dir(task_id, run_id)
            run_dir.mkdir(parents=True, exist_ok=True)
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
            state.run_count = len(state.runs)
            state.messages.append(
                ChatMessage(role="user", content=message, created_at=now, run_id=run_id)
            )
            self._write_state(state)
            return self.get_task(task_id, include_events=False), run_id

    def update_task_if_status(
        self,
        task_id: str,
        expected_statuses: set[TaskStatus],
        *,
        status: TaskStatus | None = None,
        error: str | None = None,
        needs_input: dict[str, Any] | None = None,
        append_message: ChatMessage | None = None,
        run_id: str | None = None,
        artifact_names: list[str] | None = None,
    ) -> TaskState | None:
        with self._lock:
            state = self._read_state(task_id, synthesize_legacy=True)
            if state.status not in expected_statuses:
                return None
            if run_id and state.active_run_id and state.active_run_id != run_id:
                return None
            self._apply_task_update(
                state,
                status=status,
                error=error,
                needs_input=needs_input,
                append_message=append_message,
                run_id=run_id,
                artifact_names=artifact_names,
            )
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
                raise UploadLimitError(
                    f"最多只能上传 {max_files} 个 Markdown 或 JSON 文件"
                )

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
                    if source_format_for_upload(destination) == "json":
                        validate_json_upload(temp_path, destination.name)
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
                    f"已上传 {destination.name}",
                    {"filename": destination.name, "bytes": bytes_written},
                )
            return saved_paths

    def list_uploads(self, task_id: str) -> list[Path]:
        upload_dir = self.task_dir(task_id) / "uploads"
        if not upload_dir.exists():
            return []
        return sorted(
            path
            for path in upload_dir.iterdir()
            if path.is_file() and path.suffix.lower() in UPLOAD_FORMATS
        )

    def _validate_upload_batch(
        self, task_id: str, uploads: list[UploadFile]
    ) -> list[tuple[UploadFile, str]]:
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
                        f"上传文档超过 {max_file_bytes} 字节单文件限制"
                    )
                if current_request_bytes + bytes_written > max_request_bytes:
                    raise UploadLimitError(
                        f"上传请求超过 {max_request_bytes} 字节总量限制"
                    )
                handle.write(chunk)
        return bytes_written

    def append_event(
        self,
        task_id: str,
        event_type: str,
        message: str,
        payload: dict[str, Any] | None = None,
        *,
        run_id: str | None = None,
        level: Literal["info", "success", "warning", "error"] | None = None,
    ) -> EventRecord:
        with self._lock:
            if run_id:
                validate_run_id(run_id)
            event = EventRecord(
                id=uuid.uuid4().hex,
                type=event_type,
                message=message,
                created_at=utc_now(),
                payload=payload or {},
                run_id=run_id,
                level=level,
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
            state = self._read_state(task_id, synthesize_legacy=True)
            if state.status != "running":
                return False
            run_id = state.active_run_id
            self._apply_task_update(
                state,
                status="interrupted",
                error=reason,
                needs_input=None,
                run_id=run_id,
            )
            self._write_state(state)
            self.append_event(
                task_id,
                "task_interrupted",
                reason,
                {"previous_status": "running"},
                run_id=run_id,
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

    def write_run_manifest(self, task_id: str, run_id: str, data: Any) -> Path:
        validate_run_id(run_id)
        run_path = self.run_artifact_dir(task_id, run_id) / "run.json"
        run_path.parent.mkdir(parents=True, exist_ok=True)
        run_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        self.write_json(task_id, "run.json", data)
        return run_path

    def write_run_json(self, task_id: str, run_id: str, artifact_name: str, data: Any) -> Path:
        text = json.dumps(data, ensure_ascii=False, indent=2)
        return self.write_run_text(task_id, run_id, artifact_name, text)

    def write_run_text(self, task_id: str, run_id: str, artifact_name: str, text: str) -> Path:
        name = normalize_artifact_name(artifact_name)
        validate_run_id(run_id)
        path = self.run_artifact_dir(task_id, run_id) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        if name in RUN_ARTIFACT_NAMES:
            self.write_text(task_id, f"artifacts/{name}", text)
            self.record_run_artifact(task_id, run_id, name)
        return path

    def run_artifact_dir(self, task_id: str, run_id: str) -> Path:
        validate_run_id(run_id)
        if run_id == LEGACY_RUN_ID:
            return (self.task_dir(task_id) / "artifacts").resolve()
        path = (self.task_dir(task_id) / "artifacts" / "runs" / run_id).resolve()
        runs_root = (self.task_dir(task_id) / "artifacts" / "runs").resolve()
        if runs_root not in path.parents and path != runs_root:
            raise ValueError("运行产物路径超出任务根目录")
        return path

    def record_run_artifact(self, task_id: str, run_id: str, artifact_name: str) -> None:
        name = normalize_artifact_name(artifact_name)
        validate_run_id(run_id)
        with self._lock:
            state = self._read_state(task_id, synthesize_legacy=True)
            run = self._find_run(state, run_id)
            if run is None:
                raise ValueError("未找到运行记录")
            if name not in run.artifact_names:
                run.artifact_names.append(name)
                run.artifact_names.sort()
                state.run_count = len(state.runs)
                self._write_state(state)

    def list_artifacts(self, task_id: str) -> list[ArtifactRecord]:
        with self._lock:
            return self._artifact_records_for_state(
                task_id, self._read_state(task_id, synthesize_legacy=True)
            )

    def resolve_artifact(self, task_id: str, artifact_name: str) -> Path:
        name = normalize_artifact_name(artifact_name)
        with self._lock:
            state = self._read_state(task_id, synthesize_legacy=True)
            for run in reversed(state.runs):
                if run.status == "complete" and name in run.artifact_names:
                    return self._resolve_run_artifact_path(task_id, run, name)
            legacy_path = self._resolve_top_level_artifact_path(task_id, name)
            if legacy_path.exists():
                return legacy_path
            raise FileNotFoundError(name)

    def resolve_run_artifact(self, task_id: str, run_id: str, artifact_name: str) -> Path:
        name = normalize_artifact_name(artifact_name)
        validate_run_id(run_id)
        with self._lock:
            state = self._read_state(task_id, synthesize_legacy=True)
            run = self._find_run(state, run_id)
            if run is None or name not in run.artifact_names:
                raise FileNotFoundError(name)
            return self._resolve_run_artifact_path(task_id, run, name)

    def _read_state(self, task_id: str, *, synthesize_legacy: bool = False) -> TaskState:
        data = json.loads((self.task_dir(task_id) / "state.json").read_text(encoding="utf-8"))
        data.pop("events", None)
        data.pop("artifacts", None)
        state = TaskState(**data)
        state.run_count = len(state.runs)
        if synthesize_legacy:
            state = self._synthesize_legacy_run(task_id, state)
        return state

    def _apply_task_update(
        self,
        state: TaskState,
        *,
        status: TaskStatus | None,
        error: str | None,
        needs_input: dict[str, Any] | None,
        append_message: ChatMessage | None = None,
        run_id: str | None = None,
        artifact_names: list[str] | None = None,
    ) -> None:
        now = utc_now()
        effective_run_id = run_id or state.active_run_id
        if effective_run_id:
            validate_run_id(effective_run_id)
        if status:
            state.status = status
        state.error = error
        state.needs_input = needs_input
        state.updated_at = now
        if append_message:
            if effective_run_id and append_message.run_id is None:
                append_message.run_id = effective_run_id
            state.messages.append(append_message)

        run = self._find_run(state, effective_run_id) if effective_run_id else None
        if run is not None:
            if status:
                run.status = status
                if status != "running":
                    run.completed_at = now
                    state.active_run_id = None
            run.error = error
            run.needs_input = needs_input
            if artifact_names:
                merged = set(run.artifact_names)
                merged.update(normalize_artifact_name(name) for name in artifact_names)
                run.artifact_names = sorted(merged)
        elif status and status != "running":
            state.active_run_id = None
        state.run_count = len(state.runs)

    def _synthesize_legacy_run(self, task_id: str, state: TaskState) -> TaskState:
        if state.runs:
            state.run_count = len(state.runs)
            return state
        artifact_names = self._top_level_artifact_names(task_id)
        if not artifact_names and not state.messages and state.status == "idle" and not state.error:
            state.run_count = 0
            return state

        first_user_message = next(
            (message.content for message in state.messages if message.role == "user"),
            "",
        )
        completed_at = None if state.status == "running" else state.updated_at
        state.runs = [
            TaskRunRecord(
                id=LEGACY_RUN_ID,
                status=state.status,
                message=first_user_message,
                model=state.model,
                started_at=state.created_at,
                completed_at=completed_at,
                error=state.error,
                needs_input=state.needs_input,
                artifact_base_path="artifacts",
                artifact_names=artifact_names,
            )
        ]
        for message in state.messages:
            if message.run_id is None:
                message.run_id = LEGACY_RUN_ID
        state.run_count = 1
        if state.status == "running" and state.active_run_id is None:
            state.active_run_id = LEGACY_RUN_ID
        return state

    @staticmethod
    def _find_run(state: TaskState, run_id: str | None) -> TaskRunRecord | None:
        if run_id is None:
            return None
        return next((run for run in state.runs if run.id == run_id), None)

    def _artifact_records_for_state(self, task_id: str, state: TaskState) -> list[ArtifactRecord]:
        records: list[ArtifactRecord] = []
        for run in state.runs:
            for name in run.artifact_names:
                url = (
                    f"/api/tasks/{task_id}/artifacts/{name}"
                    if run.id == LEGACY_RUN_ID
                    else f"/api/tasks/{task_id}/runs/{run.id}/artifacts/{name}"
                )
                records.append(
                    ArtifactRecord(
                        id=f"{run.id}:{name}",
                        name=name,
                        type=TYPE_MAP.get(Path(name).suffix.lower(), "text"),
                        url=url,
                        run_id=run.id,
                    )
                )
        if records:
            return sorted(records, key=lambda record: (record.run_id or "", record.name))
        names = self._top_level_artifact_names(task_id)
        return [
            ArtifactRecord(
                id=name,
                name=name,
                type=TYPE_MAP.get(Path(name).suffix.lower(), "text"),
                url=f"/api/tasks/{task_id}/artifacts/{name}",
            )
            for name in names
        ]

    def _top_level_artifact_names(self, task_id: str) -> list[str]:
        artifact_dir = self.task_dir(task_id) / "artifacts"
        if not artifact_dir.exists():
            return []
        return sorted(path.name for path in artifact_dir.iterdir() if path.is_file())

    def _resolve_top_level_artifact_path(self, task_id: str, name: str) -> Path:
        artifact_root = (self.task_dir(task_id) / "artifacts").resolve()
        path = (artifact_root / name).resolve()
        if artifact_root not in path.parents:
            raise ValueError("产物路径超出任务根目录")
        return path

    def _resolve_run_artifact_path(
        self, task_id: str, run: TaskRunRecord, artifact_name: str
    ) -> Path:
        if run.id == LEGACY_RUN_ID:
            return self._resolve_top_level_artifact_path(task_id, artifact_name)
        base = (self.task_dir(task_id) / run.artifact_base_path).resolve()
        expected_base = self.run_artifact_dir(task_id, run.id)
        if base != expected_base:
            raise ValueError("运行产物路径超出任务根目录")
        path = (base / artifact_name).resolve()
        if base not in path.parents:
            raise ValueError("产物路径超出本轮运行目录")
        return path

    def _write_state(self, state: TaskState) -> None:
        state.run_count = len(state.runs)
        data = state.model_dump()
        data["events"] = []
        data["artifacts"] = []
        path = self.task_dir(state.task_id) / "state.json"
        temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        temp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(path)
