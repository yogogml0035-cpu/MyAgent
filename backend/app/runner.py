from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from threading import Lock, Thread
from typing import Any

from .analysis import CancelledError, NeedsInputError, run_bid_analysis
from .model_provider import ModelProvider
from .permissions import PermissionPolicy
from .runtime import CancellationController
from .schemas import ChatMessage, TaskStatus
from .settings import Settings
from .storage import TaskStorage
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
                raise RuntimeError("Task is already running")
            state = self.storage.get_task(task_id, include_events=False)
            if state.status == "running":
                self.storage.mark_interrupted_if_running(
                    task_id, "Task was interrupted because no active runner owns it."
                )
                raise RuntimeError("Task was marked running without an active runner")
            if state.status not in STARTABLE_STATUSES:
                raise RuntimeError(f"Cannot start a task in {state.status} status")
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
                raise RuntimeError("Task status changed before the run could start")
            _, run_id = started
            self.storage.append_event(
                task_id,
                "user_message_received",
                "User message accepted; workflow started",
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
                    task_id, "Task was interrupted because no active runner owns it."
                ):
                    return
                self.storage.append_event(
                    task_id,
                    "cancel_ignored",
                    "Cancellation ignored because the task is not running",
                    {},
                )
                return
            controller.cancel()
        state = self.storage.get_task(task_id, include_events=False)
        run_id = state.active_run_id
        self.storage.append_event(
            task_id, "cancel_requested", "Cancellation requested", {}, run_id=run_id
        )
        updated = self.storage.update_task_if_status(
            task_id, RUNNING_STATUSES, status="cancelled", run_id=run_id
        )
        if updated is None:
            self.storage.append_event(
                task_id,
                "cancel_ignored",
                "Cancellation ignored because the task is no longer running",
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
            event_type: str, event_message: str, payload: dict[str, Any] | None = None
        ) -> None:
            self.storage.append_event(task_id, event_type, event_message, payload or {}, run_id=run_id)

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
                "Run input manifest recorded",
                {"files": [item["filename"] for item in input_manifest]},
            )
            if not uploads:
                if not requires_markdown_documents(message):
                    try:
                        reply = self.model_provider.chat(message, model, controller)
                    except RuntimeError as exc:
                        if controller.is_cancelled():
                            raise CancelledError() from exc
                        raise
                    if controller.is_cancelled():
                        raise CancelledError()
                    updated = self.storage.update_task_if_status(
                        task_id,
                        RUNNING_STATUSES,
                        status="complete",
                        append_message=ChatMessage(
                            role="assistant",
                            content=reply,
                            created_at=utc_now(),
                            run_id=run_id,
                        ),
                        run_id=run_id,
                    )
                    if updated is None:
                        if controller.is_cancelled():
                            raise CancelledError()
                        return
                    emit("chat_completed", "Simple chat response completed", {"model": model})
                    return
                raise NeedsInputError(
                    "Upload Markdown files before starting a document-analysis task.",
                    {"required_file_type": "markdown"},
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
            emit("task_completed", "Task completed", result)
        except CancelledError:
            emit("task_cancelled", "Task cancelled; intermediate artifacts were kept", {})
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
            emit("task_failed", "Task failed", {"error": str(exc)})
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
                "bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc)
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z"),
            }
        )
    return manifest


def requires_markdown_documents(message: str) -> bool:
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
