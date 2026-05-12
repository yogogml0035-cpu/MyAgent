from __future__ import annotations

import json
import re
import shutil
import threading
import uuid
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from hashlib import sha256
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Literal, TypeAlias, cast

import psycopg
from fastapi import UploadFile
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .contracts import (
    EventLevel,
    NewSessionEvent,
    SessionEvent,
    SessionSnapshot,
    artifact_ref_payload,
    build_artifact_ref,
    build_upload_resource_ref,
    resource_ref_payload,
)
from .reasoning_trace import (
    ReasoningConfidence,
    ReasoningPhase,
    build_reasoning_trace_payload,
)
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
EventAppendSpec: TypeAlias = tuple[
    str,
    str,
    dict[str, Any],
    EventLevel | None,
]
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
FILE_TOOL_AUDIT_KEYS = {
    "tool",
    "tool_name",
    "operation",
    "op",
    "requested_path",
    "virtual_path",
    "relative_path",
    "resolved_workspace_path",
    "status",
    "reason",
    "bytes",
    "sha256",
    "partial",
    "source",
    "promoted_artifact_id",
    "timestamp",
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


def parse_utc_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def format_db_timestamp(value: Any) -> str:
    if isinstance(value, datetime):
        return (
            value.astimezone(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
    if isinstance(value, str):
        return value.replace("+00:00", "Z")
    return utc_now()


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


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(UPLOAD_CHUNK_SIZE), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def summary_title(messages: list[ChatMessage]) -> str:
    for message in messages:
        if message.role != "user":
            continue
        visible = " ".join(message.content.split())
        if visible:
            return visible[:5]
    return "新对话"


def session_event_from_record(record: EventRecord) -> SessionEvent:
    if record.session_id is None:
        raise ValueError("事件缺少 session_id")
    if record.seq is None:
        raise ValueError("事件缺少 seq")
    return SessionEvent(
        id=record.id,
        session_id=record.session_id,
        seq=record.seq,
        type=record.type,
        created_at=parse_utc_timestamp(record.created_at),
        message=record.message,
        payload=record.payload,
        run_id=record.run_id,
        level=record.level,
        idempotency_key=record.idempotency_key,
    )


def _json_dict(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    return dict(value) if isinstance(value, Mapping) else None


def _json_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str)]


class PostgresTaskStorage:
    """Postgres-backed task state and event log storage.

    Structured lifecycle state lives in Postgres. Upload and artifact bytes
    remain on disk under ``task_root`` so existing file-serving and tool
    boundaries stay local to the task workspace.
    """

    def __init__(self, task_root: Path, database_url: str):
        if not database_url:
            raise ValueError("MYAGENT_DATABASE_URL 未配置")
        self.task_root = task_root.resolve()
        self.task_root.mkdir(parents=True, exist_ok=True)
        self.database_url = database_url
        self._lock = threading.RLock()

    def initialize(self) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                    CREATE TABLE IF NOT EXISTS tasks (
                        task_id TEXT PRIMARY KEY,
                        title TEXT,
                        status TEXT NOT NULL,
                        model TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL,
                        error TEXT,
                        needs_input JSONB,
                        active_run_id TEXT,
                        latest_event_seq INTEGER NOT NULL DEFAULT 0
                    )
                    """
            )
            cur.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS title TEXT")
            cur.execute(
                """
                    CREATE TABLE IF NOT EXISTS runs (
                        task_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
                        id TEXT NOT NULL,
                        status TEXT NOT NULL,
                        message TEXT NOT NULL,
                        model TEXT NOT NULL,
                        started_at TIMESTAMPTZ NOT NULL,
                        completed_at TIMESTAMPTZ,
                        error TEXT,
                        needs_input JSONB,
                        artifact_base_path TEXT NOT NULL,
                        artifact_names JSONB NOT NULL DEFAULT '[]'::jsonb,
                        PRIMARY KEY (task_id, id)
                    )
                    """
            )
            cur.execute(
                """
                    CREATE TABLE IF NOT EXISTS messages (
                        id BIGSERIAL PRIMARY KEY,
                        task_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
                        run_id TEXT,
                        role TEXT NOT NULL,
                        content TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL,
                        level TEXT
                    )
                    """
            )
            cur.execute(
                """
                    CREATE TABLE IF NOT EXISTS events (
                        id TEXT PRIMARY KEY,
                        task_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
                        seq INTEGER NOT NULL,
                        type TEXT NOT NULL,
                        message TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL,
                        payload JSONB NOT NULL DEFAULT '{}'::jsonb,
                        run_id TEXT,
                        level TEXT,
                        idempotency_key TEXT,
                        UNIQUE (task_id, seq)
                    )
                    """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_events_task_seq ON events(task_id, seq)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_events_task_id ON events(task_id, id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_runs_task ON runs(task_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_messages_task ON messages(task_id, id)")

    def _connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

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
        task_dir = self.task_dir(task_id)
        for child in ("uploads", "artifacts", "subagents", "logs"):
            (task_dir / child).mkdir(parents=True, exist_ok=True)
        with self._lock, self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                    INSERT INTO tasks (
                        task_id, status, model, created_at, updated_at, latest_event_seq
                    )
                    VALUES (%s, %s, %s, %s, %s, 0)
                    """,
                (task_id, "idle", model, now, now),
            )
            self._append_event_with_cursor(
                cur,
                task_id,
                "task_created",
                "任务目录已创建。",
                {"model": model},
            )
        return self.get_task(task_id)

    def get_task(self, task_id: str, *, include_events: bool = True) -> TaskState:
        with self._lock, self._connect() as conn, conn.cursor() as cur:
            state = self._state_from_db(cur, task_id, include_events=include_events)
            return state

    def list_task_summaries(self) -> list[TaskSummary]:
        with self._lock, self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM tasks ORDER BY updated_at DESC, created_at DESC, task_id DESC")
            summaries: list[TaskSummary] = []
            for row in cur.fetchall():
                state = self._state_from_row(cur, row, include_events=False)
                if not any(
                    message.role == "user" and message.content.strip() for message in state.messages
                ):
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
            return summaries

    def rename_task(self, task_id: str, title: str) -> TaskState:
        normalized = " ".join(title.split())
        if not normalized:
            raise ValueError("会话名称不能为空")
        if len(normalized) > 80:
            raise ValueError("会话名称不能超过 80 个字符")
        with self._lock, self._connect() as conn, conn.cursor() as cur:
            self._fetch_task_row(cur, task_id, lock=True)
            cur.execute("UPDATE tasks SET title = %s WHERE task_id = %s", (normalized, task_id))
        return self.get_task(task_id, include_events=False)

    def delete_task(self, task_id: str) -> None:
        task_path = self.task_dir(task_id)
        with self._lock, self._connect() as conn, conn.cursor() as cur:
            self._fetch_task_row(cur, task_id, lock=True)
            cur.execute("DELETE FROM tasks WHERE task_id = %s", (task_id,))
        shutil.rmtree(task_path, ignore_errors=True)

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
        with self._lock, self._connect() as conn, conn.cursor() as cur:
            self._fetch_task_row(cur, task_id, lock=True)
            self._apply_task_update(
                cur,
                task_id,
                status=status,
                error=error,
                needs_input=needs_input,
                append_message=append_message,
                run_id=run_id,
                artifact_names=artifact_names,
            )
        return self.get_task(task_id)

    def start_run(
        self,
        task_id: str,
        *,
        message: str,
        model: str,
        expected_statuses: set[TaskStatus],
    ) -> tuple[TaskState, str] | None:
        with self._lock, self._connect() as conn, conn.cursor() as cur:
            row = self._fetch_task_row(cur, task_id, lock=True)
            if row["status"] not in expected_statuses:
                return None
            now = utc_now()
            run_id = generate_run_id()
            run_dir = self.run_artifact_dir(task_id, run_id)
            run_dir.mkdir(parents=True, exist_ok=True)
            cur.execute(
                """
                    UPDATE tasks
                    SET status = %s,
                        model = %s,
                        error = NULL,
                        needs_input = NULL,
                        active_run_id = %s,
                        updated_at = %s
                    WHERE task_id = %s
                    """,
                ("running", model, run_id, now, task_id),
            )
            cur.execute(
                """
                    INSERT INTO runs (
                        task_id, id, status, message, model, started_at, artifact_base_path
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                (
                    task_id,
                    run_id,
                    "running",
                    message,
                    model,
                    now,
                    f"artifacts/runs/{run_id}",
                ),
            )
            self._insert_message(
                cur,
                task_id,
                ChatMessage(role="user", content=message, created_at=now, run_id=run_id),
                run_id,
            )
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
        return self.update_task_if_status_and_append_events(
            task_id,
            expected_statuses,
            events=[],
            status=status,
            error=error,
            needs_input=needs_input,
            append_message=append_message,
            run_id=run_id,
            artifact_names=artifact_names,
        )

    def update_task_if_status_and_append_events(
        self,
        task_id: str,
        expected_statuses: set[TaskStatus],
        *,
        events: Iterable[EventAppendSpec],
        status: TaskStatus | None = None,
        error: str | None = None,
        needs_input: dict[str, Any] | None = None,
        append_message: ChatMessage | None = None,
        run_id: str | None = None,
        artifact_names: list[str] | None = None,
    ) -> TaskState | None:
        with self._lock, self._connect() as conn, conn.cursor() as cur:
            row = self._fetch_task_row(cur, task_id, lock=True)
            if row["status"] not in expected_statuses:
                return None
            active_run_id = row.get("active_run_id")
            if run_id and active_run_id and active_run_id != run_id:
                return None
            self._apply_task_update(
                cur,
                task_id,
                status=status,
                error=error,
                needs_input=needs_input,
                append_message=append_message,
                run_id=run_id,
                artifact_names=artifact_names,
            )
            for event_type, event_message, event_payload, event_level in events:
                self._append_event_with_cursor(
                    cur,
                    task_id,
                    event_type,
                    event_message,
                    event_payload,
                    run_id=run_id,
                    level=event_level,
                )
        return self.get_task(task_id)

    def update_task_if_status_and_append_event(
        self,
        task_id: str,
        expected_statuses: set[TaskStatus],
        *,
        event_type: str,
        event_message: str,
        event_payload: dict[str, Any] | None = None,
        event_level: Literal["info", "success", "warning", "error"] | None = None,
        status: TaskStatus | None = None,
        error: str | None = None,
        needs_input: dict[str, Any] | None = None,
        append_message: ChatMessage | None = None,
        run_id: str | None = None,
        artifact_names: list[str] | None = None,
    ) -> TaskState | None:
        return self.update_task_if_status_and_append_events(
            task_id,
            expected_statuses,
            events=[(event_type, event_message, event_payload or {}, event_level)],
            status=status,
            error=error,
            needs_input=needs_input,
            append_message=append_message,
            run_id=run_id,
            artifact_names=artifact_names,
        )

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
            self.get_task(task_id, include_events=False)
            upload_dir = self.task_dir(task_id) / "uploads"
            upload_dir.mkdir(parents=True, exist_ok=True)
            if len(self.list_uploads(task_id)) + len(uploads) > max_files:
                raise UploadLimitError(f"最多只能上传 {max_files} 个 Markdown 或 JSON 文件")

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
                    raise UploadLimitError(f"上传文档超过 {max_file_bytes} 字节单文件限制")
                if current_request_bytes + bytes_written > max_request_bytes:
                    raise UploadLimitError(f"上传请求超过 {max_request_bytes} 字节总量限制")
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
        level: EventLevel | None = None,
    ) -> EventRecord:
        with self._lock, self._connect() as conn, conn.cursor() as cur:
            return self._append_event_with_cursor(
                cur,
                task_id,
                event_type,
                message,
                payload or {},
                run_id=run_id,
                level=level,
            )

    def emit_event(self, session_id: str, event: NewSessionEvent) -> SessionEvent:
        with self._lock, self._connect() as conn, conn.cursor() as cur:
            record = self._append_event_with_cursor(
                cur,
                session_id,
                event.type,
                event.message,
                event.payload,
                run_id=event.run_id,
                level=event.level,
                idempotency_key=event.idempotency_key,
            )
            return session_event_from_record(record)

    def get_session(self, session_id: str) -> SessionSnapshot:
        with self._lock, self._connect() as conn, conn.cursor() as cur:
            row = self._fetch_task_row(cur, session_id, lock=False)
            return SessionSnapshot(
                session_id=session_id,
                created_at=parse_utc_timestamp(format_db_timestamp(row["created_at"])),
                latest_seq=int(row["latest_event_seq"]),
                metadata={"model": row["model"], "status": row["status"]},
            )

    def get_events(
        self,
        session_id: str,
        *,
        after_seq: int | None = None,
        limit: int | None = None,
        reverse: bool = False,
    ) -> list[SessionEvent]:
        events = [session_event_from_record(event) for event in self.read_events(session_id)]
        if after_seq is not None:
            events = [event for event in events if event.seq > after_seq]
        if reverse:
            events = list(reversed(events))
        if limit is not None:
            events = events[: max(0, limit)]
        return events

    def create_session(self, metadata: dict[str, Any]) -> SessionSnapshot:
        model = str(metadata.get("model") or "deepseek:deepseek-chat")
        state = self.create_task(None, model)
        return self.get_session(state.task_id)

    def append_file_tool_audit(
        self, task_id: str, run_id: str | None, record: Mapping[str, Any]
    ) -> EventRecord:
        payload = dict(record)
        payload["run_id"] = run_id
        missing = FILE_TOOL_AUDIT_KEYS.difference(payload)
        if missing:
            raise ValueError(f"文件工具审计记录缺少字段：{', '.join(sorted(missing))}")
        status = payload.get("status")
        level: EventLevel = "info"
        if status in {"denied", "cancelled"}:
            level = "warning"
        elif status == "failed":
            level = "error"
        return self.append_event(
            task_id,
            "file_tool_audit",
            "已记录文件工具访问审计。",
            payload,
            run_id=run_id,
            level=level,
        )

    def append_reasoning_trace(
        self,
        task_id: str,
        run_id: str,
        *,
        agent_id: str,
        phase: ReasoningPhase,
        summary: str,
        confidence: ReasoningConfidence | None = None,
        evidence_refs: Iterable[Any] | None = None,
        source_event_id: str | None = None,
    ) -> EventRecord:
        payload = build_reasoning_trace_payload(
            agent_id=agent_id,
            phase=phase,
            summary=summary,
            confidence=confidence,
            evidence_refs=evidence_refs,
            source_event_id=source_event_id,
        )
        return self.append_event(
            task_id,
            "reasoning_trace",
            f"{payload['agent_id']} 已记录思考摘要。",
            payload,
            run_id=run_id,
        )

    def read_events(self, task_id: str, *, after_id: str | None = None) -> list[EventRecord]:
        with self._lock, self._connect() as conn, conn.cursor() as cur:
            self._fetch_task_row(cur, task_id, lock=False)
            if after_id is None:
                cur.execute(
                    "SELECT * FROM events WHERE task_id = %s ORDER BY seq ASC",
                    (task_id,),
                )
            else:
                cur.execute(
                    """
                        SELECT seq FROM events
                        WHERE task_id = %s AND id = %s
                        """,
                    (task_id, after_id),
                )
                after_row = cur.fetchone()
                if after_row is None:
                    return []
                cur.execute(
                    """
                        SELECT * FROM events
                        WHERE task_id = %s AND seq > %s
                        ORDER BY seq ASC
                        """,
                    (task_id, after_row["seq"]),
                )
            return [self._event_record_from_row(row) for row in cur.fetchall()]

    def list_task_ids(self) -> list[str]:
        with self._lock, self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT task_id FROM tasks ORDER BY task_id ASC")
            return [str(row["task_id"]) for row in cur.fetchall()]

    def interrupt_running_tasks(self, reason: str) -> list[str]:
        interrupted = []
        for task_id in self.list_task_ids():
            if self.mark_interrupted_if_running(task_id, reason):
                interrupted.append(task_id)
        return interrupted

    def mark_interrupted_if_running(self, task_id: str, reason: str) -> bool:
        state = self.get_task(task_id, include_events=False)
        run_id = state.active_run_id
        updated = self.update_task_if_status_and_append_event(
            task_id,
            {"running"},
            event_type="task_interrupted",
            event_message=reason,
            event_payload={"previous_status": "running"},
            event_level="warning",
            status="interrupted",
            error=reason,
            needs_input=None,
            run_id=run_id,
        )
        return updated is not None

    def write_json(self, task_id: str, relative_path: str, data: Any) -> Path:
        path = self._task_relative_path(task_id, relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def write_text(self, task_id: str, relative_path: str, text: str) -> Path:
        path = self._task_relative_path(task_id, relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def _task_relative_path(self, task_id: str, relative_path: str) -> Path:
        if not relative_path:
            raise ValueError("任务相对路径不能为空")
        candidate = Path(relative_path)
        if candidate.is_absolute():
            raise ValueError("任务相对路径不能是绝对路径")
        task_dir = self.task_dir(task_id)
        path = (task_dir / candidate).resolve()
        if task_dir not in path.parents:
            raise ValueError("任务相对路径超出任务目录")
        return path

    def write_run_manifest(self, task_id: str, run_id: str, data: Any) -> Path:
        validate_run_id(run_id)
        run_path = self.run_artifact_dir(task_id, run_id) / "run.json"
        run_path.parent.mkdir(parents=True, exist_ok=True)
        run_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        self.write_json(task_id, "run.json", data)
        return run_path

    def _read_run_manifest(self, task_id: str, run_id: str) -> dict[str, Any]:
        run_path = self.run_artifact_dir(task_id, run_id) / "run.json"
        if not run_path.exists():
            return {}
        try:
            data = json.loads(run_path.read_text(encoding="utf-8"))
        except (JSONDecodeError, UnicodeDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _merge_run_manifest_artifact_ref(
        self,
        task_id: str,
        run_id: str,
        artifact_ref: dict[str, Any],
    ) -> None:
        manifest = self._read_run_manifest(task_id, run_id)
        refs = manifest.get("artifact_refs")
        artifact_refs = [item for item in refs if isinstance(item, dict)] if isinstance(refs, list) else []
        artifact_id = artifact_ref.get("id")
        artifact_refs = [item for item in artifact_refs if item.get("id") != artifact_id]
        artifact_refs.append(artifact_ref)
        manifest["artifact_refs"] = sorted(
            artifact_refs,
            key=lambda item: str(item.get("name") or item.get("id") or ""),
        )
        self.write_run_manifest(task_id, run_id, manifest)

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
            self.record_run_artifact(
                task_id,
                run_id,
                name,
                artifact_ref=self._artifact_ref_payload(task_id, run_id, name, path),
            )
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

    def _artifact_ref_payload(
        self,
        task_id: str,
        run_id: str,
        artifact_name: str,
        artifact_path: Path,
    ) -> dict[str, Any]:
        artifact_ref = build_artifact_ref(
            session_id=task_id,
            run_id=run_id,
            name=artifact_name,
            artifact_type=TYPE_MAP.get(Path(artifact_name).suffix.lower(), "text"),
            size_bytes=artifact_path.stat().st_size if artifact_path.exists() else None,
            digest=file_sha256(artifact_path) if artifact_path.exists() else None,
        )
        return artifact_ref_payload(artifact_ref)

    def record_run_artifact(
        self,
        task_id: str,
        run_id: str,
        artifact_name: str,
        *,
        artifact_ref: dict[str, Any] | None = None,
    ) -> None:
        name = normalize_artifact_name(artifact_name)
        validate_run_id(run_id)
        with self._lock, self._connect() as conn, conn.cursor() as cur:
            run = self._fetch_run_row(cur, task_id, run_id)
            if run is None:
                raise ValueError("未找到运行记录")
            if artifact_ref is None:
                artifact_path = self.run_artifact_dir(task_id, run_id) / name
                if artifact_path.exists():
                    artifact_ref = self._artifact_ref_payload(
                        task_id, run_id, name, artifact_path
                    )
            names = set(_json_list(run["artifact_names"]))
            if name not in names:
                names.add(name)
                cur.execute(
                    """
                        UPDATE runs
                        SET artifact_names = %s
                        WHERE task_id = %s AND id = %s
                        """,
                    (Jsonb(sorted(names)), task_id, run_id),
                )
        if artifact_ref is not None:
            self._merge_run_manifest_artifact_ref(task_id, run_id, artifact_ref)

    def list_artifacts(self, task_id: str) -> list[ArtifactRecord]:
        return self.get_task(task_id, include_events=False).artifacts

    def resolve_artifact(self, task_id: str, artifact_name: str) -> Path:
        name = normalize_artifact_name(artifact_name)
        state = self.get_task(task_id, include_events=False)
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
        state = self.get_task(task_id, include_events=False)
        run = self._find_run(state, run_id)
        if run is None or name not in run.artifact_names:
            raise FileNotFoundError(name)
        return self._resolve_run_artifact_path(task_id, run, name)

    def _fetch_task_row(self, cur, task_id: str, *, lock: bool) -> dict[str, Any]:
        suffix = " FOR UPDATE" if lock else ""
        cur.execute(f"SELECT * FROM tasks WHERE task_id = %s{suffix}", (task_id,))
        row = cur.fetchone()
        if row is None:
            raise FileNotFoundError(task_id)
        return cast("dict[str, Any]", row)

    def _fetch_run_row(self, cur, task_id: str, run_id: str) -> dict[str, Any] | None:
        cur.execute("SELECT * FROM runs WHERE task_id = %s AND id = %s", (task_id, run_id))
        row = cur.fetchone()
        return cast("dict[str, Any] | None", row)

    def _state_from_db(self, cur, task_id: str, *, include_events: bool) -> TaskState:
        row = self._fetch_task_row(cur, task_id, lock=False)
        return self._state_from_row(cur, row, include_events=include_events)

    def _state_from_row(self, cur, row: Mapping[str, Any], *, include_events: bool) -> TaskState:
        task_id = str(row["task_id"])
        cur.execute("SELECT * FROM runs WHERE task_id = %s ORDER BY started_at ASC, id ASC", (task_id,))
        runs = [self._run_record_from_row(run_row) for run_row in cur.fetchall()]
        cur.execute("SELECT * FROM messages WHERE task_id = %s ORDER BY id ASC", (task_id,))
        messages = [self._message_from_row(message_row) for message_row in cur.fetchall()]
        events: list[EventRecord] = []
        if include_events:
            cur.execute("SELECT * FROM events WHERE task_id = %s ORDER BY seq ASC", (task_id,))
            events = [self._event_record_from_row(event_row) for event_row in cur.fetchall()]
        state = TaskState(
            task_id=task_id,
            title=cast("str | None", row.get("title")),
            status=cast(TaskStatus, row["status"]),
            model=str(row["model"]),
            created_at=format_db_timestamp(row["created_at"]),
            updated_at=format_db_timestamp(row["updated_at"]),
            messages=messages,
            events=events,
            runs=runs,
            active_run_id=cast("str | None", row["active_run_id"]),
            run_count=len(runs),
            upload_count=len(self.list_uploads(task_id)),
            error=cast("str | None", row["error"]),
            needs_input=_json_dict(row["needs_input"]),
        )
        state.artifacts = self._artifact_records_for_state(task_id, state)
        return state

    def _run_record_from_row(self, row: Mapping[str, Any]) -> TaskRunRecord:
        return TaskRunRecord(
            id=str(row["id"]),
            status=cast(TaskStatus, row["status"]),
            message=str(row["message"]),
            model=str(row["model"]),
            started_at=format_db_timestamp(row["started_at"]),
            completed_at=(
                format_db_timestamp(row["completed_at"]) if row.get("completed_at") is not None else None
            ),
            error=cast("str | None", row["error"]),
            needs_input=_json_dict(row["needs_input"]),
            artifact_base_path=str(row["artifact_base_path"]),
            artifact_names=_json_list(row["artifact_names"]),
        )

    def _message_from_row(self, row: Mapping[str, Any]) -> ChatMessage:
        return ChatMessage(
            role=cast(Literal["user", "assistant", "system"], row["role"]),
            content=str(row["content"]),
            created_at=format_db_timestamp(row["created_at"]),
            run_id=cast("str | None", row["run_id"]),
            level=cast("Literal['info', 'warning', 'error'] | None", row["level"]),
        )

    def _event_record_from_row(self, row: Mapping[str, Any]) -> EventRecord:
        return EventRecord(
            id=str(row["id"]),
            session_id=str(row["task_id"]),
            seq=int(row["seq"]),
            type=str(row["type"]),
            message=str(row["message"]),
            created_at=format_db_timestamp(row["created_at"]),
            payload=dict(row["payload"]) if isinstance(row["payload"], Mapping) else {},
            run_id=cast("str | None", row["run_id"]),
            level=cast("Literal['info', 'success', 'warning', 'error'] | None", row["level"]),
            idempotency_key=cast("str | None", row["idempotency_key"]),
        )

    def _append_event_with_cursor(
        self,
        cur,
        task_id: str,
        event_type: str,
        message: str,
        payload: dict[str, Any],
        *,
        run_id: str | None = None,
        level: EventLevel | None = None,
        idempotency_key: str | None = None,
    ) -> EventRecord:
        if run_id:
            validate_run_id(run_id)
        cur.execute(
            """
            UPDATE tasks
            SET latest_event_seq = latest_event_seq + 1
            WHERE task_id = %s
            RETURNING latest_event_seq
            """,
            (task_id,),
        )
        seq_row = cur.fetchone()
        if seq_row is None:
            raise FileNotFoundError(task_id)
        seq = int(seq_row["latest_event_seq"])
        event = EventRecord(
            id=uuid.uuid4().hex,
            session_id=task_id,
            seq=seq,
            type=event_type,
            message=message,
            created_at=utc_now(),
            payload=payload,
            run_id=run_id,
            level=level,
            idempotency_key=idempotency_key,
        )
        cur.execute(
            """
            INSERT INTO events (
                id, task_id, seq, type, message, created_at, payload, run_id, level, idempotency_key
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                event.id,
                task_id,
                seq,
                event_type,
                message,
                event.created_at,
                Jsonb(payload),
                run_id,
                level,
                idempotency_key,
            ),
        )
        return event

    def _apply_task_update(
        self,
        cur,
        task_id: str,
        *,
        status: TaskStatus | None,
        error: str | None,
        needs_input: dict[str, Any] | None,
        append_message: ChatMessage | None = None,
        run_id: str | None = None,
        artifact_names: list[str] | None = None,
    ) -> None:
        now = utc_now()
        cur.execute("SELECT active_run_id FROM tasks WHERE task_id = %s", (task_id,))
        task_row = cur.fetchone()
        if task_row is None:
            raise FileNotFoundError(task_id)
        effective_run_id = run_id or task_row.get("active_run_id")
        if effective_run_id:
            validate_run_id(str(effective_run_id))
        active_run_id = None if status and status != "running" else effective_run_id
        task_status_sql = "status = COALESCE(%s, status),"
        cur.execute(
            f"""
            UPDATE tasks
            SET {task_status_sql}
                error = %s,
                needs_input = %s,
                active_run_id = %s,
                updated_at = %s
            WHERE task_id = %s
            """,
            (
                status,
                error,
                Jsonb(needs_input) if needs_input is not None else None,
                active_run_id,
                now,
                task_id,
            ),
        )
        if append_message:
            if effective_run_id and append_message.run_id is None:
                append_message.run_id = str(effective_run_id)
            self._insert_message(cur, task_id, append_message, append_message.run_id)

        if effective_run_id:
            run = self._fetch_run_row(cur, task_id, str(effective_run_id))
            if run is not None:
                completed_at = now if status and status != "running" else run.get("completed_at")
                names = set(_json_list(run["artifact_names"]))
                if artifact_names:
                    names.update(normalize_artifact_name(name) for name in artifact_names)
                cur.execute(
                    """
                    UPDATE runs
                    SET status = COALESCE(%s, status),
                        completed_at = %s,
                        error = %s,
                        needs_input = %s,
                        artifact_names = %s
                    WHERE task_id = %s AND id = %s
                    """,
                    (
                        status,
                        completed_at,
                        error,
                        Jsonb(needs_input) if needs_input is not None else None,
                        Jsonb(sorted(names)),
                        task_id,
                        effective_run_id,
                    ),
                )

    def _insert_message(
        self, cur, task_id: str, message: ChatMessage, run_id: str | None
    ) -> None:
        cur.execute(
            """
            INSERT INTO messages (task_id, run_id, role, content, created_at, level)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                task_id,
                run_id,
                message.role,
                message.content,
                message.created_at or utc_now(),
                message.level,
            ),
        )

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


TaskStorage = PostgresTaskStorage
