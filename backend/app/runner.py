from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from threading import Lock, Thread
from typing import Any, Literal

from .analysis import CancelledError, NeedsInputError, run_bid_analysis
from .model_provider import ModelProvider, is_model_configuration_warning
from .permissions import PermissionPolicy
from .runtime import CancellationController
from .schemas import ChatMessage, TaskStatus
from .settings import Settings
from .storage import TaskStorage, source_format_for_upload
from .tools import WorkspaceTools

STARTABLE_STATUSES: set[TaskStatus] = {
    "idle",
    "needs_input",
    "complete",
    "failed",
    "cancelled",
    "interrupted",
}
RUNNING_STATUSES: set[TaskStatus] = {"running"}


class TaskRunner:
    def __init__(self, storage: TaskStorage, model_provider: ModelProvider, settings: Settings):
        self.storage = storage
        self.model_provider = model_provider
        self.settings = settings
        self._lock = Lock()
        self._threads: dict[str, Thread] = {}
        self._controllers: dict[str, CancellationController] = {}

    def start(self, task_id: str, message: str, model: str) -> None:
        with self._lock:
            existing = self._threads.get(task_id)
            if existing and existing.is_alive():
                raise RuntimeError("任务正在运行中")
            state = self.storage.get_task(task_id, include_events=False)
            if state.status == "running":
                self.storage.mark_interrupted_if_running(
                    task_id, "任务已中断：当前没有运行器接管该任务。"
                )
                raise RuntimeError("任务被标记为运行中，但没有活动运行器接管")
            if state.status not in STARTABLE_STATUSES:
                raise RuntimeError(f"任务处于 {state.status} 状态，不能启动新运行")
            controller = CancellationController()
            self._controllers[task_id] = controller
            started = self.storage.start_run(
                task_id,
                message=message,
                model=model,
                expected_statuses=STARTABLE_STATUSES,
            )
            if started is None:
                self._controllers.pop(task_id, None)
                raise RuntimeError("运行启动前任务状态已变化")
            _, run_id = started
            self.storage.append_event(
                task_id,
                "user_message_received",
                "已接收用户消息，工作流开始执行。",
                {"model": model, "message": message},
                run_id=run_id,
            )
            thread = Thread(
                target=self._run,
                name=f"agent-task-{task_id}",
                args=(task_id, run_id, message, model, controller),
                daemon=True,
            )
            self._threads[task_id] = thread
            thread.start()

    def cancel(self, task_id: str) -> None:
        with self._lock:
            thread = self._threads.get(task_id)
            controller = self._controllers.get(task_id)
            if controller is None or thread is None or not thread.is_alive():
                if self.storage.mark_interrupted_if_running(
                    task_id, "任务已中断：当前没有运行器接管该任务。"
                ):
                    return
                self.storage.append_event(
                    task_id,
                    "cancel_ignored",
                    "任务未在运行，已忽略取消请求。",
                    {},
                )
                return
            controller.cancel()
        state = self.storage.get_task(task_id, include_events=False)
        run_id = state.active_run_id
        self.storage.append_event(
            task_id, "cancel_requested", "已请求取消任务。", {}, run_id=run_id
        )
        updated = self.storage.update_task_if_status(
            task_id, RUNNING_STATUSES, status="cancelled", run_id=run_id
        )
        if updated is None:
            self.storage.append_event(
                task_id,
                "cancel_ignored",
                "任务已不再运行，已忽略取消请求。",
                {},
            )

    def is_running(self, task_id: str) -> bool:
        with self._lock:
            thread = self._threads.get(task_id)
            return bool(thread and thread.is_alive())

    def _run(
        self, task_id: str, run_id: str, message: str, model: str, controller: CancellationController
    ) -> None:
        def emit(
            event_type: str,
            event_message: str,
            payload: dict[str, Any] | None = None,
            *,
            level: Literal["info", "success", "warning", "error"] | None = None,
        ) -> None:
            self.storage.append_event(
                task_id, event_type, event_message, payload or {}, run_id=run_id, level=level
            )

        try:
            uploads = self.storage.list_uploads(task_id)
            input_manifest = build_input_manifest(uploads)
            run_manifest = {
                "started_at": utc_now(),
                "model": model,
                "message": message,
                "inputs": input_manifest,
            }
            self.storage.write_run_manifest(task_id, run_id, run_manifest)
            emit(
                "run_manifest_created",
                "已记录本轮输入清单。",
                {"files": [item["filename"] for item in input_manifest]},
            )
            if not uploads:
                if not requires_document_uploads(message):
                    try:
                        reply = self.model_provider.chat(message, model, controller)
                    except RuntimeError as exc:
                        if controller.is_cancelled():
                            raise CancelledError() from exc
                        raise
                    if controller.is_cancelled():
                        raise CancelledError()
                    warning_reply = is_model_configuration_warning(reply)
                    if warning_reply:
                        emit(
                            "model_warning",
                            "模型服务配置提醒。",
                            {"model": model, "code": "missing_provider_key"},
                            level="warning",
                        )
                    updated = self.storage.update_task_if_status(
                        task_id,
                        RUNNING_STATUSES,
                        status="complete",
                        append_message=ChatMessage(
                            role="assistant",
                            content=reply,
                            created_at=utc_now(),
                            run_id=run_id,
                            level="warning" if warning_reply else None,
                        ),
                        run_id=run_id,
                    )
                    if updated is None:
                        if controller.is_cancelled():
                            raise CancelledError()
                        return
                    emit("chat_completed", "简单对话回复已完成。", {"model": model})
                    return
                raise NeedsInputError(
                    "开始文档分析任务前，请先上传 Markdown 或 JSON 文件。",
                    {"required_file_type": "markdown_or_json"},
                )
            result = run_bid_analysis(
                task_id=task_id,
                run_id=run_id,
                uploads=uploads,
                task_message=message,
                model=model,
                model_provider=self.model_provider,
                storage=self.storage,
                controller=controller,
                workspace_tools=WorkspaceTools(
                    self.storage.task_dir(task_id),
                    PermissionPolicy(self.storage.task_dir(task_id)),
                    self.settings.tavily_api_key,
                    controller,
                ),
                emit=emit,
            )
            if controller.is_cancelled():
                raise CancelledError()
            assistant_text = (
                "分析完成。可以打开本轮 `report.html` 查看交互式对比报告。"
                f"证据记录：{result['evidence_count']} 条。"
            )
            updated = self.storage.update_task_if_status(
                task_id,
                RUNNING_STATUSES,
                status="complete",
                append_message=ChatMessage(
                    role="assistant",
                    content=assistant_text,
                    created_at=utc_now(),
                    run_id=run_id,
                ),
                run_id=run_id,
                artifact_names=result.get("artifacts"),
            )
            if updated is None:
                if controller.is_cancelled():
                    raise CancelledError()
                return
            emit("task_completed", "任务已完成。", result)
        except CancelledError:
            emit("task_cancelled", "任务已取消，已保留中间产物。", {})
            self.storage.update_task_if_status(
                task_id, RUNNING_STATUSES, status="cancelled", run_id=run_id
            )
        except NeedsInputError as exc:
            payload = {"message": str(exc), **exc.payload}
            emit("needs_input", str(exc), payload)
            self.storage.update_task_if_status(
                task_id,
                RUNNING_STATUSES,
                status="needs_input",
                needs_input=payload,
                run_id=run_id,
            )
        except Exception as exc:
            emit("task_failed", "任务执行失败。", {"error": str(exc)})
            self.storage.update_task_if_status(
                task_id, RUNNING_STATUSES, status="failed", error=str(exc), run_id=run_id
            )
        finally:
            with self._lock:
                self._controllers.pop(task_id, None)
                self._threads.pop(task_id, None)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_input_manifest(uploads: list[Path]) -> list[dict[str, Any]]:
    manifest: list[dict[str, Any]] = []
    for path in uploads:
        stat = path.stat()
        manifest.append(
            {
                "filename": path.name,
                "relative_path": f"uploads/{path.name}",
                "source_format": source_format_for_upload(path),
                "size_bytes": stat.st_size,
                "bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc)
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z"),
            }
        )
    return manifest


def requires_document_uploads(message: str) -> bool:
    markers = [
        "串标",
        "围标",
        "投标",
        "招标",
        "bid",
        "tender",
        "document",
        "文件",
        "报告",
    ]
    lowered = message.lower()
    return any(marker.lower() in lowered for marker in markers)
