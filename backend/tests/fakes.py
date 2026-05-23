from __future__ import annotations

import copy
import json
import shutil
import uuid
from pathlib import Path
from typing import Any, Literal

from fastapi import UploadFile

from app.schemas import (
    ArtifactRecord,
    ChatMessage,
    EventRecord,
    TaskRunRecord,
    TaskState,
    TaskStatus,
    TaskSummary,
)
from app.storage import (
    LEGACY_RUN_ID,
    RUN_ARTIFACT_NAMES,
    SUPPORTED_UPLOAD_LABEL,
    TASK_FILE_WORKSPACE_DIRS,
    TYPE_MAP,
    UPLOAD_CHUNK_SIZE,
    UPLOAD_FORMATS,
    AgentStoreItem,
    LongTermMemoryRecord,
    ToolResultCacheRecord,
    UploadConflictError,
    UploadLimitError,
    build_upload_resource_ref,
    document_upload_filename,
    file_sha256,
    generate_run_id,
    normalize_artifact_name,
    resource_ref_payload,
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
        self.context_summaries: dict[str, str] = {}
        self.agent_store_items: dict[tuple[tuple[str, ...], str], AgentStoreItem] = {}
        self.tool_caches: dict[str, ToolResultCacheRecord] = {}
        self.long_term_memories: dict[str, LongTermMemoryRecord] = {}

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
        for child in TASK_FILE_WORKSPACE_DIRS:
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
        events = state.events
        state.latest_event_id = events[-1].id if events else None
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

    def set_task_title_if_empty(self, task_id: str, title: str) -> TaskState:
        state = self.states[task_id]
        normalized = " ".join(title.split())[:80]
        if normalized and not state.title:
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

    def read_events(
        self,
        task_id: str,
        *,
        after_id: str | None = None,
        run_id: str | None = None,
    ) -> list[EventRecord]:
        if run_id is not None:
            validate_run_id(run_id)
        events = list(self.states[task_id].events)
        if after_id is None:
            filtered = events
        else:
            filtered = events
            for index, event in enumerate(events):
                if event.id == after_id:
                    filtered = events[index + 1 :]
                    break
        if run_id is not None:
            filtered = [event for event in filtered if event.run_id == run_id]
        return copy.deepcopy(filtered)

    def get_task_messages(self, task_id: str) -> list[ChatMessage]:
        return self.get_task(task_id, include_events=False).messages

    def get_context_summary(self, task_id: str) -> str | None:
        return self.context_summaries.get(task_id)

    def upsert_context_summary(
        self, task_id: str, summary: str, *, covered_message_count: int
    ) -> None:
        self.context_summaries[task_id] = summary

    def cache_tool_result(
        self,
        task_id: str,
        *,
        tool_name: str,
        query: str,
        result_text: str,
        ttl_seconds: int,
    ) -> ToolResultCacheRecord:
        from datetime import datetime, timedelta, timezone

        now_dt = datetime.now(timezone.utc).replace(microsecond=0)
        expires_dt = now_dt + timedelta(seconds=ttl_seconds)
        record = ToolResultCacheRecord(
            cache_id=f"cache-{uuid.uuid4().hex}",
            task_id=task_id,
            tool_name=tool_name,
            query=query,
            result_text=result_text,
            created_at=now_dt.isoformat().replace("+00:00", "Z"),
            expires_at=expires_dt.isoformat().replace("+00:00", "Z"),
        )
        self.tool_caches[f"{task_id}:{tool_name}:{query}"] = record
        return record

    def get_fresh_tool_cache(
        self, task_id: str, *, tool_name: str, query: str
    ) -> ToolResultCacheRecord | None:
        return self.tool_caches.get(f"{task_id}:{tool_name}:{query}")

    def list_fresh_tool_cache(self, task_id: str, *, limit: int = 5) -> list[ToolResultCacheRecord]:
        items = [record for record in self.tool_caches.values() if record.task_id == task_id]
        return copy.deepcopy(sorted(items, key=lambda record: record.created_at, reverse=True)[:limit])

    def put_agent_store_item(
        self, namespace: tuple[str, ...], key: str, value: dict[str, Any]
    ) -> AgentStoreItem:
        now = utc_now()
        existing = self.agent_store_items.get((namespace, key))
        item = AgentStoreItem(
            namespace=namespace,
            key=key,
            value=copy.deepcopy(value),
            created_at=existing.created_at if existing else now,
            updated_at=now,
        )
        self.agent_store_items[(namespace, key)] = item
        return item

    def delete_agent_store_item(self, namespace: tuple[str, ...], key: str) -> None:
        self.agent_store_items.pop((namespace, key), None)

    def get_agent_store_item(self, namespace: tuple[str, ...], key: str) -> AgentStoreItem | None:
        return copy.deepcopy(self.agent_store_items.get((namespace, key)))

    def search_agent_store_items(
        self,
        namespace_prefix: tuple[str, ...],
        *,
        limit: int = 10,
        offset: int = 0,
        filter: dict[str, Any] | None = None,
    ) -> list[AgentStoreItem]:
        items = [
            item
            for (namespace, _), item in self.agent_store_items.items()
            if namespace[: len(namespace_prefix)] == namespace_prefix
        ]
        if filter:
            items = [
                item
                for item in items
                if all(item.value.get(key) == value for key, value in filter.items())
            ]
        return copy.deepcopy(sorted(items, key=lambda item: (item.namespace, item.key))[offset : offset + limit])

    def list_agent_store_namespaces(
        self,
        *,
        prefix: tuple[str, ...] | None = None,
        suffix: tuple[str, ...] | None = None,
        max_depth: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[tuple[str, ...]]:
        namespaces = {namespace for namespace, _ in self.agent_store_items}
        if prefix:
            namespaces = {namespace for namespace in namespaces if namespace[: len(prefix)] == prefix}
        if suffix:
            namespaces = {namespace for namespace in namespaces if namespace[-len(suffix) :] == suffix}
        if max_depth is not None:
            namespaces = {namespace[:max_depth] for namespace in namespaces}
        return sorted(namespaces)[offset : offset + limit]

    def put_long_term_memory(
        self,
        *,
        memory_id: str,
        user_id: str,
        memory_type: str,
        text: str,
        confidence: float,
        source_task_id: str,
        source_run_id: str,
    ) -> LongTermMemoryRecord:
        now = utc_now()
        existing = self.long_term_memories.get(memory_id)
        record = LongTermMemoryRecord(
            memory_id=memory_id,
            user_id=user_id,
            memory_type=memory_type,
            text=text,
            confidence=confidence,
            source_task_id=source_task_id,
            source_run_id=source_run_id,
            created_at=existing.created_at if existing else now,
            updated_at=now,
        )
        self.long_term_memories[memory_id] = record
        return record

    def get_long_term_memory(self, memory_id: str) -> LongTermMemoryRecord | None:
        return copy.deepcopy(self.long_term_memories.get(memory_id))

    def list_long_term_memories(
        self, *, limit: int = 1000, offset: int = 0, user_id: str | None = None
    ) -> list[LongTermMemoryRecord]:
        records = list(self.long_term_memories.values())
        if user_id:
            records = [record for record in records if record.user_id == user_id]
        records = sorted(records, key=lambda record: (record.created_at, record.memory_id))
        return copy.deepcopy(records[offset : offset + limit])

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
        if name in RUN_ARTIFACT_NAMES:
            self.write_text(task_id, f"artifacts/{name}", text)
        self.record_run_artifact(task_id, run_id, name)
        return path

    def promote_run_artifact_file(
        self,
        task_id: str,
        run_id: str,
        source_path: str,
        artifact_name: str | None = None,
    ) -> Path:
        validate_run_id(run_id)
        source = self._task_relative_path(task_id, source_path)
        if not source.exists() or not source.is_file():
            raise FileNotFoundError(source_path)
        task_dir = self.task_dir(task_id)
        artifacts_root = (task_dir / "artifacts").resolve()
        if artifacts_root in source.parents:
            raise ValueError("源文件不能位于产物目录")

        name = normalize_artifact_name(artifact_name or source.name)
        destination = self.run_artifact_dir(task_id, run_id) / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        if name in RUN_ARTIFACT_NAMES:
            legacy_destination = self._task_relative_path(task_id, f"artifacts/{name}")
            legacy_destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(destination, legacy_destination)
        self.record_run_artifact(task_id, run_id, name)
        return destination

    def run_artifact_dir(self, task_id: str, run_id: str) -> Path:
        validate_run_id(run_id)
        if run_id == LEGACY_RUN_ID:
            return (self.task_dir(task_id) / "artifacts").resolve()
        return (self.task_dir(task_id) / "artifacts" / "runs" / run_id).resolve()

    def record_run_artifact(self, task_id: str, run_id: str, artifact_name: str, **_kwargs) -> None:
        name = normalize_artifact_name(artifact_name)
        validate_run_id(run_id)
        state = self.states[task_id]
        for run in state.runs:
            if run.id == run_id:
                if name not in run.artifact_names:
                    run.artifact_names.append(name)
                    run.artifact_names.sort()
                return
        raise ValueError("未找到运行记录")

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

    @staticmethod
    def _find_run(state: TaskState, run_id: str | None) -> TaskRunRecord | None:
        if run_id is None:
            return None
        return next((run for run in state.runs if run.id == run_id), None)

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
        return [
            ArtifactRecord(
                id=name,
                name=name,
                type=TYPE_MAP.get(Path(name).suffix.lower(), "text"),
                url=f"/api/tasks/{task_id}/artifacts/{name}",
            )
            for name in self._top_level_artifact_names(task_id)
        ]

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
                merged.update(normalize_artifact_name(name) for name in artifact_names)
                run.artifact_names = sorted(merged)

    def _task_relative_path(self, task_id: str, relative_path: str) -> Path:
        path = (self.task_dir(task_id) / relative_path).resolve()
        if self.task_dir(task_id) not in path.parents:
            raise ValueError("任务相对路径超出任务目录")
        return path
