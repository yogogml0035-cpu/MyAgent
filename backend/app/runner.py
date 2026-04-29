from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from threading import Lock, Thread
from typing import Any, Literal

from .analysis import CancelledError, NeedsInputError, run_bid_analysis
from .deep_agent_runtime import DeepAgentUnavailableError
from .intent import InputScope, TaskMode, route_intent
from .model_provider import ModelProvider, is_model_configuration_warning
from .orchestrator import DeepAgentOrchestrator
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

    def start(
        self,
        task_id: str,
        message: str,
        model: str,
        *,
        mode: TaskMode = "auto",
        input_scope: InputScope = "auto",
    ) -> None:
        resolved_mode = mode
        resolved_input_scope = input_scope
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
                {
                    "model": model,
                    "message": message,
                    "mode": resolved_mode,
                    "input_scope": resolved_input_scope,
                },
                run_id=run_id,
            )
            thread = Thread(
                target=self._run,
                name=f"agent-task-{task_id}",
                args=(
                    task_id,
                    run_id,
                    message,
                    model,
                    resolved_mode,
                    resolved_input_scope,
                    controller,
                ),
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
        self,
        task_id: str,
        run_id: str,
        message: str,
        model: str,
        mode: TaskMode,
        input_scope: InputScope,
        controller: CancellationController,
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
            available_input_manifest = build_input_manifest(uploads)
            decision = route_intent(
                message,
                mode=mode,
                input_scope=input_scope,
                has_uploads=bool(uploads),
            )
            selected_uploads = uploads if decision.use_uploads else []
            selected_upload_names = {path.name for path in selected_uploads}
            input_manifest = [
                item
                for item in available_input_manifest
                if item["filename"] in selected_upload_names
            ]
            run_manifest = {
                "started_at": utc_now(),
                "model": model,
                "message": message,
                "mode": mode,
                "intent": decision.as_manifest(),
                "input_scope": decision.input_scope_manifest(),
                "inputs": input_manifest,
                "available_uploads": available_input_manifest,
                "selected_uploads": [path.name for path in selected_uploads],
            }
            self.storage.write_run_manifest(task_id, run_id, run_manifest)
            emit(
                "run_manifest_created",
                "已记录本轮输入清单。",
                {
                    "files": [item["filename"] for item in input_manifest],
                    "intent": decision.intent,
                    "route": decision.route,
                    "input_scope": decision.resolved_input_scope,
                },
            )
            if decision.route == "chat" or decision.route == "search":
                reply, warning_code = self._run_simple_message(
                    task_id,
                    message,
                    model,
                    decision.route,
                    controller,
                )
                warning_reply = warning_code is not None or is_model_configuration_warning(reply)
                if warning_reply:
                    warning_event_type = (
                        "model_warning" if decision.route == "chat" else "search_warning"
                    )
                    warning_message = (
                        "模型服务配置提醒。"
                        if decision.route == "chat"
                        else "搜索服务配置提醒。"
                    )
                    emit(
                        warning_event_type,
                        warning_message,
                        {"model": model, "code": warning_code or "missing_provider_key"},
                        level="warning",
                    )
                if self._complete_with_assistant_message(
                    task_id,
                    run_id,
                    reply,
                    level="warning" if warning_reply else None,
                    completion_event_type=(
                        "chat_completed" if decision.route == "chat" else "search_completed"
                    ),
                    completion_event_message=(
                        "简单对话回复已完成。"
                        if decision.route == "chat"
                        else "轻量搜索回复已完成。"
                    ),
                    completion_event_payload={"model": model},
                ):
                    pass
                elif controller.is_cancelled():
                    raise CancelledError()
                return

            if decision.route == "deep_agent":
                try:
                    orchestrator = DeepAgentOrchestrator(
                        storage=self.storage,
                        task_id=task_id,
                        run_id=run_id,
                        model=model,
                        controller=controller,
                        uploads=selected_uploads,
                    )
                    deep_agent_result = orchestrator.run(message)
                    artifact_names = deep_agent_result.metadata.get("promoted_artifacts")
                    if not isinstance(artifact_names, list):
                        artifact_names = []
                    if self._complete_with_assistant_message(
                        task_id,
                        run_id,
                        deep_agent_result.output_text,
                        artifact_names=[str(name) for name in artifact_names],
                        completion_event_type="deep_agent_completed",
                        completion_event_message="DeepAgent 运行已完成。",
                        completion_event_payload=deep_agent_result.metadata,
                    ):
                        pass
                    elif controller.is_cancelled():
                        raise CancelledError()
                except DeepAgentUnavailableError as exc:
                    reply = f"{exc} 本轮没有读取历史上传文件，也没有启动文档分析子任务。"
                    emit(
                        "deep_agent_unavailable",
                        "DeepAgent 运行库不可用。",
                        {"code": "missing_deepagents_dependency"},
                        level="warning",
                    )
                    if should_fallback_deep_agent_to_document_analysis(decision.reason):
                        fallback_manifest = {
                            **run_manifest,
                            "intent": fallback_document_intent_manifest(decision.reason),
                            "deep_agent_fallback": {
                                "reason": "missing_deepagents_dependency",
                                "message": "DeepAgent 运行库不可用，已使用确定性文档分析兼容路径。",
                            },
                        }
                        self.storage.write_run_manifest(task_id, run_id, fallback_manifest)
                        emit(
                            "deep_agent_fallback",
                            "DeepAgent 运行库不可用，已使用确定性文档分析兼容路径。",
                            {"fallback_route": "document_analysis"},
                            level="warning",
                        )
                    else:
                        self._complete_with_assistant_message(
                            task_id, run_id, reply, level="warning"
                        )
                        return
                else:
                    return

            if not selected_uploads:
                raise NeedsInputError(
                    "开始文档分析任务前，请先上传 Markdown 或 JSON 文件。",
                    {"required_file_type": "markdown_or_json"},
                )
            bid_result = run_bid_analysis(
                task_id=task_id,
                run_id=run_id,
                uploads=selected_uploads,
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
                f"证据记录：{bid_result['evidence_count']} 条。"
            )
            completed = self._complete_with_assistant_message(
                task_id,
                run_id,
                assistant_text,
                artifact_names=bid_result.get("artifacts"),
                completion_event_type="task_completed",
                completion_event_message="任务已完成。",
                completion_event_payload=bid_result,
            )
            if not completed and controller.is_cancelled():
                raise CancelledError()
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

    def _run_simple_message(
        self,
        task_id: str,
        message: str,
        model: str,
        route: Literal["chat", "search"],
        controller: CancellationController,
    ) -> tuple[str, str | None]:
        if route == "search":
            workspace_tools = WorkspaceTools(
                self.storage.task_dir(task_id),
                PermissionPolicy(self.storage.task_dir(task_id)),
                self.settings.tavily_api_key,
                controller,
            )
            result = workspace_tools.tavily_search(message)
            warning = result.get("warning")
            if isinstance(warning, str) and warning:
                return (
                    "联网搜索未启用：后端未配置 TAVILY_API_KEY。"
                    "本轮已按轻量搜索请求处理，没有读取历史上传文件，也没有启动文档分析。",
                    "missing_tavily_key",
                )
            return render_search_reply(result), None

        try:
            reply = self.model_provider.chat(message, model, controller)
        except RuntimeError as exc:
            if controller.is_cancelled():
                raise CancelledError() from exc
            raise
        if controller.is_cancelled():
            raise CancelledError()
        warning_code = "missing_provider_key" if is_model_configuration_warning(reply) else None
        return reply, warning_code

    def _complete_with_assistant_message(
        self,
        task_id: str,
        run_id: str,
        content: str,
        *,
        level: Literal["info", "warning", "error"] | None = None,
        artifact_names: list[str] | None = None,
        completion_event_type: str | None = None,
        completion_event_message: str = "",
        completion_event_payload: dict[str, Any] | None = None,
        completion_event_level: Literal["info", "success", "warning", "error"] | None = None,
    ) -> bool:
        if completion_event_type:
            updated = self.storage.update_task_if_status_and_append_event(
                task_id,
                RUNNING_STATUSES,
                status="complete",
                append_message=ChatMessage(
                    role="assistant",
                    content=content,
                    created_at=utc_now(),
                    run_id=run_id,
                    level=level,
                ),
                run_id=run_id,
                artifact_names=artifact_names,
                event_type=completion_event_type,
                event_message=completion_event_message,
                event_payload=completion_event_payload,
                event_level=completion_event_level,
            )
            return updated is not None
        updated = self.storage.update_task_if_status(
            task_id,
            RUNNING_STATUSES,
            status="complete",
            append_message=ChatMessage(
                role="assistant",
                content=content,
                created_at=utc_now(),
                run_id=run_id,
                level=level,
            ),
            run_id=run_id,
            artifact_names=artifact_names,
        )
        return updated is not None


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
    return route_intent(message).requires_uploads


def should_fallback_deep_agent_to_document_analysis(reason: str) -> bool:
    return reason in {"upload_reference_marker", "document_analysis_marker"}


def fallback_document_intent_manifest(reason: str) -> dict[str, object]:
    intent_name = "continue_with_uploads" if reason == "upload_reference_marker" else "document_analysis"
    return {
        "mode": "auto",
        "name": intent_name,
        "route": "document_analysis",
        "requires_uploads": True,
        "reason": f"{reason}_deep_agent_unavailable_fallback",
    }


def render_search_reply(result: dict[str, Any]) -> str:
    items = result.get("results")
    if not isinstance(items, list) or not items:
        return "没有检索到可用结果。本轮没有读取历史上传文件，也没有启动文档分析。"

    lines = ["已完成轻量联网检索，本轮没有读取历史上传文件。"]
    for index, item in enumerate(items[:5], start=1):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "未命名结果")
        url = str(item.get("url") or "")
        content = str(item.get("content") or item.get("snippet") or "").strip()
        summary = f"{index}. {title}"
        if url:
            summary += f" - {url}"
        if content:
            summary += f"\n   {content[:240]}"
        lines.append(summary)
    return "\n".join(lines)
