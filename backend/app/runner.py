from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock, Thread
from typing import Any, Literal, TypeAlias

from .agent_activity import (
    build_live_answer_status_metadata,
    build_live_status_metadata,
    build_live_tool_call_metadata,
    build_live_tool_result_metadata,
)
from .agent_profiles import (
    AgentProfile,
    agent_profile_manifest,
    profile_decision_summary,
    select_agent_profile,
)
from .analysis import CancelledError, NeedsInputError, run_bid_analysis
from .deep_agent_runtime import DeepAgentUnavailableError
from .intent import InputScope, TaskMode, route_intent
from .model_provider import ModelProvider, is_model_configuration_warning
from .orchestrator import DeepAgentOrchestrator
from .permissions import PermissionPolicy
from .reasoning_trace import (
    ReasoningConfidence,
    ReasoningPhase,
    build_reasoning_trace_payload,
    sanitize_reasoning_text,
)
from .runtime import CancellationController
from .schemas import ChatMessage, TaskStatus
from .settings import Settings
from .storage import EventAppendSpec, TaskStorage, source_format_for_upload
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
SEARCH_SOURCE_LIMIT = 5
SEARCH_SNIPPET_CHARS = 320
SEARCH_TITLE_CHARS = 140
SEARCH_URL_CHARS = 360
SEARCH_SYNTHESIS_ANSWER_CHARS = 4000
ORCHESTRATION_TENDER_MARKERS = ("tender", "招标", "采购", "需求书")
RUN_REASONING_AGENT_ID = "task-run"

Emit = Callable[..., None]
TerminalReasoning: TypeAlias = tuple[ReasoningPhase, str, ReasoningConfidence, list[str]]


@dataclass(frozen=True)
class SearchSourceSummary:
    title: str
    url: str
    snippet: str

    def to_payload(self) -> dict[str, str]:
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
        }


@dataclass(frozen=True)
class SearchSynthesisResult:
    answer: str
    sources: list[SearchSourceSummary]
    used_model: bool
    warning_code: str | None = None

    @property
    def event_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "used_model": self.used_model,
            "source_count": len(self.sources),
            "sources": [source.to_payload() for source in self.sources],
        }
        if self.warning_code:
            payload["warning_code"] = self.warning_code
        return payload


@dataclass(frozen=True)
class SimpleMessageResult:
    answer: str
    warning_code: str | None = None
    completion_payload: dict[str, Any] | None = None


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
        reasoning_events: list[EventAppendSpec] = []
        if run_id:
            reasoning_events = self._run_reasoning_event_specs(
                task_id,
                run_id,
                phase="risk",
                summary="任务已取消，已保留当前可用的安全运行记录。",
                confidence="medium",
            )
        updated = self.storage.update_task_if_status_and_append_events(
            task_id,
            RUNNING_STATUSES,
            events=reasoning_events,
            status="cancelled",
            run_id=run_id,
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
            selected_upload_name_list = [path.name for path in selected_uploads]
            bidder_count = estimate_bidder_count(selected_upload_name_list)
            agent_profile = select_agent_profile(
                decision=decision,
                selected_upload_names=selected_upload_name_list,
                bidder_count=bidder_count,
                message=message,
            )
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
                "selected_uploads": selected_upload_name_list,
                "agent_profile": agent_profile_manifest(agent_profile),
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
                    "chosen_profile_id": agent_profile.id if agent_profile else None,
                    "live": build_live_status_metadata(
                        agent_name="task_agent",
                        stage="analyzing_intent",
                    ),
                },
            )
            emit(
                "orchestration_decision",
                "已记录本轮编排策略。",
                {
                    **build_orchestration_decision_payload(
                        route=decision.route,
                        reason=decision.reason,
                        selected_upload_names=selected_upload_name_list,
                        message=message,
                        agent_profile=agent_profile,
                        bidder_count=bidder_count,
                    ),
                    "live": build_live_status_metadata(
                        agent_name="task_agent",
                        stage="selecting_tool",
                    ),
                },
            )
            if decision.route == "chat" or decision.route == "search":
                simple_result = self._run_simple_message(
                    task_id,
                    message,
                    model,
                    decision.route,
                    controller,
                    emit,
                )
                reply = simple_result.answer
                warning_code = simple_result.warning_code
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
                    terminal_reasoning=self._simple_terminal_reasoning(
                        route=decision.route,
                        result=simple_result,
                        warning_reply=warning_reply,
                    ),
                    completion_event_type=(
                        "chat_completed" if decision.route == "chat" else "search_completed"
                    ),
                    completion_event_message=(
                        "简单对话回复已完成。"
                        if decision.route == "chat"
                        else "轻量搜索回复已完成。"
                    ),
                    completion_event_payload={
                        "model": model,
                        **(simple_result.completion_payload or {}),
                    },
                ):
                    pass
                elif controller.is_cancelled():
                    raise CancelledError()
                return

            if decision.route == "deep_agent":
                try:
                    if agent_profile is None:
                        raise RuntimeError("DeepAgent 路由缺少 Agent Profile")
                    orchestrator = DeepAgentOrchestrator(
                        storage=self.storage,
                        task_id=task_id,
                        run_id=run_id,
                        model=model,
                        controller=controller,
                        uploads=selected_uploads,
                        agent_profile=agent_profile,
                    )
                    deep_agent_result = orchestrator.run(message)
                    artifact_names = deep_agent_result.metadata.get("promoted_artifacts")
                    if not isinstance(artifact_names, list):
                        artifact_names = []
                    deep_agent_warning = bool(deep_agent_result.metadata.get("warning_code"))
                    if self._complete_with_assistant_message(
                        task_id,
                        run_id,
                        deep_agent_result.output_text,
                        level="warning" if deep_agent_warning else None,
                        artifact_names=[str(name) for name in artifact_names],
                        terminal_reasoning=(
                            (
                                "risk",
                                "DeepAgent 已完成但返回运行提醒；详情仅记录安全元数据。",
                                "medium",
                                [str(name) for name in artifact_names],
                            )
                            if deep_agent_warning
                            else (
                                "final_summary",
                                f"DeepAgent 已完成本轮任务并提升 {len(artifact_names)} 个输出产物。",
                                "medium" if artifact_names else "low",
                                [str(name) for name in artifact_names],
                            )
                        ),
                        completion_event_type="deep_agent_completed",
                        completion_event_message="DeepAgent 运行已完成。",
                        completion_event_payload=deep_agent_result.metadata,
                        completion_event_level="warning" if deep_agent_warning else None,
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
                            "agent_profile": agent_profile_manifest(agent_profile),
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
                            task_id,
                            run_id,
                            reply,
                            level="warning",
                            terminal_reasoning=(
                                "risk",
                                "DeepAgent 运行库不可用，本轮未启动 DeepAgent 执行。",
                                "medium",
                                [],
                            ),
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
                terminal_reasoning=(
                    "final_summary",
                    (
                        "文档分析已完成，已生成结构化证据和本轮报告产物。"
                    ),
                    "medium",
                    [str(name) for name in bid_result.get("artifacts") or []],
                ),
                completion_event_type="task_completed",
                completion_event_message="任务已完成。",
                completion_event_payload={
                    **bid_result,
                    "live": build_live_answer_status_metadata(
                        agent_name="analysis_agent",
                        stage="completed",
                        result_status="success",
                    ),
                },
            )
            if not completed and controller.is_cancelled():
                raise CancelledError()
        except CancelledError:
            self._append_run_reasoning_trace_if_absent(
                task_id,
                run_id,
                phase="risk",
                summary="任务已取消，已保留当前可用的安全运行记录。",
                confidence="medium",
            )
            emit(
                "task_cancelled",
                "任务已取消，已保留中间产物。",
                {
                    "live": build_live_status_metadata(
                        agent_name="task_agent",
                        stage="failed",
                        result_status="cancelled",
                    )
                },
            )
            self.storage.update_task_if_status(
                task_id, RUNNING_STATUSES, status="cancelled", run_id=run_id
            )
        except NeedsInputError as exc:
            payload = {
                "message": str(exc),
                **exc.payload,
                "live": build_live_status_metadata(
                    agent_name="task_agent",
                    stage="needs_input",
                ),
            }
            self.storage.update_task_if_status_and_append_events(
                task_id,
                RUNNING_STATUSES,
                events=[
                    *self._run_reasoning_event_specs(
                        task_id,
                        run_id,
                        phase="next_step",
                        summary=(
                            "当前请求需要补充输入后才能继续执行；"
                            "请按提示上传或提供所需材料。"
                        ),
                        confidence="high",
                        evidence_refs=[
                            str(payload.get("required_file_type") or "required_input")
                        ],
                    ),
                    ("needs_input", str(exc), payload, None),
                ],
                status="needs_input",
                needs_input=payload,
                run_id=run_id,
            )
        except Exception as exc:
            safe_error = bounded_safe_text(str(exc), 240)
            self.storage.update_task_if_status_and_append_events(
                task_id,
                RUNNING_STATUSES,
                status="failed",
                error=safe_error,
                run_id=run_id,
                events=[
                    *self._run_reasoning_event_specs(
                        task_id,
                        run_id,
                        phase="risk",
                        summary=f"任务执行失败，已停止本轮运行：{safe_error}",
                        confidence="medium",
                    ),
                    (
                        "task_failed",
                        "任务执行失败。",
                        {
                            "error": safe_error,
                            "live": build_live_status_metadata(
                                agent_name="task_agent",
                                stage="failed",
                                result_status="failed",
                            ),
                        },
                        None,
                    ),
                ],
            )
        finally:
            with self._lock:
                self._controllers.pop(task_id, None)
                self._threads.pop(task_id, None)

    def _simple_terminal_reasoning(
        self,
        *,
        route: Literal["chat", "search"],
        result: SimpleMessageResult,
        warning_reply: bool,
    ) -> TerminalReasoning:
        payload = result.completion_payload or {}
        used_model = payload.get("used_model")
        warning_code = result.warning_code or payload.get("warning_code")
        if route == "chat":
            if warning_reply:
                return (
                    "risk",
                    "简单对话已返回配置提醒，实时模型回复未完成；本轮未读取上传文件。",
                    "medium",
                    [str(warning_code or "missing_provider_key")],
                )
            return (
                "final_summary",
                "简单对话已完成模型回复；本轮未调用搜索或文档分析工具。",
                "medium",
                [],
            )

        sources = payload.get("sources") if isinstance(payload, dict) else None
        source_titles = safe_search_source_titles(sources)
        source_count = payload.get("source_count")
        resolved_source_count = source_count if isinstance(source_count, int) else len(source_titles)
        if warning_reply or used_model is False or resolved_source_count == 0:
            return (
                "risk",
                (
                    "轻量搜索已结束但存在限制："
                    f"模型合成={'未使用' if used_model is False else '已使用'}，"
                    f"安全来源数 {resolved_source_count}；本轮未读取上传文件。"
                ),
                "medium",
                [str(warning_code)] if warning_code else source_titles,
            )
        return (
            "final_summary",
            (
                f"轻量搜索已基于 {resolved_source_count} 个安全来源完成模型合成；"
                "本轮未读取上传文件。"
            ),
            "medium",
            source_titles,
        )

    def _has_reasoning_trace(self, task_id: str, run_id: str, phase: ReasoningPhase) -> bool:
        for event in self.storage.read_events(task_id):
            if event.type != "reasoning_trace" or event.run_id != run_id:
                continue
            if event.payload.get("phase") == phase:
                return True
        return False

    def _run_reasoning_event_specs(
        self,
        task_id: str,
        run_id: str,
        *,
        phase: ReasoningPhase,
        summary: str,
        confidence: ReasoningConfidence,
        evidence_refs: list[str] | None = None,
    ) -> list[EventAppendSpec]:
        if self._has_reasoning_trace(task_id, run_id, phase):
            return []
        payload = build_reasoning_trace_payload(
            agent_id=RUN_REASONING_AGENT_ID,
            phase=phase,
            summary=summary,
            confidence=confidence,
            evidence_refs=evidence_refs or [],
        )
        return [("reasoning_trace", f"{payload['agent_id']} 已记录思考摘要。", payload, None)]

    def _append_run_reasoning_trace_if_absent(
        self,
        task_id: str,
        run_id: str,
        *,
        phase: ReasoningPhase,
        summary: str,
        confidence: ReasoningConfidence,
        evidence_refs: list[str] | None = None,
    ) -> None:
        if self._has_reasoning_trace(task_id, run_id, phase):
            return
        self.storage.append_reasoning_trace(
            task_id,
            run_id,
            agent_id=RUN_REASONING_AGENT_ID,
            phase=phase,
            summary=summary,
            confidence=confidence,
            evidence_refs=evidence_refs or [],
        )

    def _run_simple_message(
        self,
        task_id: str,
        message: str,
        model: str,
        route: Literal["chat", "search"],
        controller: CancellationController,
        emit: Emit,
    ) -> SimpleMessageResult:
        if route == "search":
            search_tool_call_id = "search_tool_1"
            workspace_tools = WorkspaceTools(
                self.storage.task_dir(task_id),
                PermissionPolicy(self.storage.task_dir(task_id)),
                self.settings.tavily_api_key,
                controller,
            )
            search_parameters = {
                "query": bounded_safe_text(message, 240),
                "max_results": SEARCH_SOURCE_LIMIT,
                "use_uploads": False,
            }
            emit(
                "search_tool_call",
                "已调用联网搜索工具。",
                {
                    "tool_name": "tavily_search",
                    "parameter_summary": search_parameters,
                    "live": build_live_tool_call_metadata(
                        agent_name="search_agent",
                        tool_name="tavily_search",
                        tool_call_id=search_tool_call_id,
                        parameters=search_parameters,
                    ),
                },
            )
            result = workspace_tools.tavily_search(message)
            warning = result.get("warning")
            sources = summarize_search_sources(result)
            warning_code = "missing_tavily_key" if isinstance(warning, str) and warning else None
            emit(
                "search_tool_result",
                "联网搜索工具已返回安全摘要。",
                {
                    "tool_name": "tavily_search",
                    "result_count": len(sources),
                    "sources": [source.to_payload() for source in sources],
                    "live": build_live_tool_result_metadata(
                        agent_name="search_agent",
                        tool_name="tavily_search",
                        tool_call_id=search_tool_call_id,
                        result=result,
                        result_status="failed" if warning_code else None,
                        result_count=len(sources),
                    ),
                    **({"warning_code": warning_code} if warning_code else {}),
                },
                level="warning" if warning_code else None,
            )
            emit(
                "answer_generation_started",
                "正在生成回答。",
                {
                    "live": build_live_answer_status_metadata(
                        agent_name="search_agent",
                        stage="generating_answer",
                    )
                },
            )
            synthesis = self._synthesize_search_result(
                message=message,
                model=model,
                sources=sources,
                warning_code=warning_code,
                controller=controller,
            )
            synthesis_payload = {
                **synthesis.event_payload,
                "live": build_live_answer_status_metadata(
                    agent_name="search_agent",
                    stage="completed",
                    result_status="skipped" if synthesis.warning_code else "success",
                ),
            }
            emit(
                "search_synthesis_completed",
                "已根据搜索结果生成最终回答。",
                synthesis_payload,
                level="warning" if synthesis.warning_code else "success",
            )
            return SimpleMessageResult(
                answer=synthesis.answer,
                warning_code=synthesis.warning_code,
                completion_payload=synthesis.event_payload,
            )

        emit(
            "answer_generation_started",
            "正在生成回答。",
            {
                "live": build_live_answer_status_metadata(
                    agent_name="main_agent",
                    stage="generating_answer",
                )
            },
        )
        try:
            reply = self.model_provider.chat(message, model, controller)
        except RuntimeError as exc:
            if controller.is_cancelled():
                raise CancelledError() from exc
            raise
        if controller.is_cancelled():
            raise CancelledError()
        warning_code = "missing_provider_key" if is_model_configuration_warning(reply) else None
        return SimpleMessageResult(
            answer=reply,
            warning_code=warning_code,
            completion_payload={
                "used_model": warning_code is None,
                "live": build_live_answer_status_metadata(
                    agent_name="main_agent",
                    stage="completed",
                    result_status="skipped" if warning_code else "success",
                ),
            },
        )

    def _synthesize_search_result(
        self,
        *,
        message: str,
        model: str,
        sources: list[SearchSourceSummary],
        warning_code: str | None,
        controller: CancellationController,
    ) -> SearchSynthesisResult:
        if warning_code == "missing_tavily_key":
            return SearchSynthesisResult(
                answer=(
                    "联网搜索未启用：后端未配置 TAVILY_API_KEY。"
                    "本轮已按轻量搜索请求处理，没有读取历史上传文件，也没有启动文档分析。"
                ),
                sources=[],
                used_model=False,
                warning_code=warning_code,
            )
        if not sources:
            return SearchSynthesisResult(
                answer=(
                    "没有检索到可用结果。本轮没有读取历史上传文件，也没有启动文档分析。"
                ),
                sources=[],
                used_model=False,
            )

        prompt = build_search_synthesis_prompt(message, sources)
        try:
            answer = self.model_provider.chat(prompt, model, controller)
        except Exception as exc:
            if controller.is_cancelled():
                raise CancelledError() from exc
            return SearchSynthesisResult(
                answer=render_search_fallback_answer(
                    message,
                    sources,
                    "模型合成暂不可用：本轮已保留联网检索摘要，但未能调用模型生成完整回答。",
                ),
                sources=sources,
                used_model=False,
                warning_code="model_synthesis_failed",
            )
        if controller.is_cancelled():
            raise CancelledError()
        if is_model_configuration_warning(answer):
            return SearchSynthesisResult(
                answer=render_search_fallback_answer(
                    message,
                    sources,
                    "模型合成未启用：后端未配置 DEEPSEEK_API_KEY。",
                ),
                sources=sources,
                used_model=False,
                warning_code="missing_provider_key",
            )
        answer = bounded_safe_text(answer, SEARCH_SYNTHESIS_ANSWER_CHARS)
        if not answer:
            return SearchSynthesisResult(
                answer=render_search_fallback_answer(
                    message,
                    sources,
                    "模型没有返回可用内容，以下为联网检索的安全摘要。",
                ),
                sources=sources,
                used_model=False,
                warning_code="empty_model_response",
            )
        return SearchSynthesisResult(
            answer=answer,
            sources=sources,
            used_model=True,
        )

    def _complete_with_assistant_message(
        self,
        task_id: str,
        run_id: str,
        content: str,
        *,
        level: Literal["info", "warning", "error"] | None = None,
        artifact_names: list[str] | None = None,
        terminal_reasoning: TerminalReasoning | None = None,
        completion_event_type: str | None = None,
        completion_event_message: str = "",
        completion_event_payload: dict[str, Any] | None = None,
        completion_event_level: Literal["info", "success", "warning", "error"] | None = None,
    ) -> bool:
        events: list[EventAppendSpec] = []
        if terminal_reasoning is not None:
            phase, summary, confidence, evidence_refs = terminal_reasoning
            events.extend(
                self._run_reasoning_event_specs(
                    task_id,
                    run_id,
                    phase=phase,
                    summary=summary,
                    confidence=confidence,
                    evidence_refs=evidence_refs,
                )
            )
        if completion_event_type:
            events.append(
                (
                    completion_event_type,
                    completion_event_message,
                    completion_event_payload or {},
                    completion_event_level,
                )
            )
            updated = self.storage.update_task_if_status_and_append_events(
                task_id,
                RUNNING_STATUSES,
                events=events,
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
        if events:
            updated = self.storage.update_task_if_status_and_append_events(
                task_id,
                RUNNING_STATUSES,
                events=events,
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


def build_orchestration_decision_payload(
    *,
    route: str,
    reason: str,
    selected_upload_names: list[str],
    message: str,
    agent_profile: AgentProfile | None = None,
    bidder_count: int | None = None,
) -> dict[str, Any]:
    resolved_bidder_count = (
        bidder_count if bidder_count is not None else estimate_bidder_count(selected_upload_names)
    )
    uses_complex_files = route in {"deep_agent", "document_analysis"} and resolved_bidder_count >= 2
    strategy = agent_profile.strategy if agent_profile is not None else (
        "multi_agent" if uses_complex_files else "single_agent"
    )
    planned_subagents = (
        agent_profile.planned_subagents
        if agent_profile is not None
        else [
            "document-classification",
            "requirement-matching",
            "bidder-pair-comparison",
            "evidence-normalization",
            "report-writing",
        ]
        if uses_complex_files
        else []
    )
    if route == "search":
        reason_code = "simple_search_no_uploads"
        decision_summary = profile_decision_summary(agent_profile, resolved_bidder_count, route)
    elif uses_complex_files:
        reason_code = agent_profile.reason_code if agent_profile is not None else "multi_document_bid_comparison"
        decision_summary = profile_decision_summary(agent_profile, resolved_bidder_count, route)
    elif route == "deep_agent":
        reason_code = agent_profile.reason_code if agent_profile is not None else "file_aware_single_agent"
        decision_summary = profile_decision_summary(agent_profile, resolved_bidder_count, route)
    else:
        reason_code = "simple_chat"
        decision_summary = profile_decision_summary(agent_profile, resolved_bidder_count, route)
    return {
        "schema_version": 1,
        "strategy": strategy,
        "reason_code": reason_code,
        "input_count": len(selected_upload_names),
        "bidder_count": resolved_bidder_count,
        "planned_subagents": planned_subagents,
        "decision_summary": sanitize_reasoning_text(decision_summary, max_chars=360),
        "route": route,
        "route_reason": sanitize_reasoning_text(reason, max_chars=120),
        "message_class": classify_message_for_decision(message),
        "chosen_profile_id": agent_profile.id if agent_profile is not None else None,
        "chosen_profile_label": agent_profile.label if agent_profile is not None else None,
    }


def classify_message_for_decision(message: str) -> str:
    folded = message.casefold()
    if any(token in folded for token in ("天气", "搜索", "查一下", "检索", "search")):
        return "search_or_lookup"
    if any(token in folded for token in ("串标", "围标", "投标", "招标", "bid")):
        return "bid_or_document_analysis"
    return "general"


def estimate_bidder_count(upload_names: list[str]) -> int:
    if not upload_names:
        return 0
    tender_count = sum(1 for name in upload_names if is_likely_tender_filename(name))
    return max(0, len(upload_names) - tender_count)


def is_likely_tender_filename(name: str) -> bool:
    folded = name.casefold()
    return any(marker in folded for marker in ORCHESTRATION_TENDER_MARKERS)


def safe_search_source_titles(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    titles: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        title = bounded_safe_text(item.get("title") or "", SEARCH_TITLE_CHARS)
        if title:
            titles.append(title)
        if len(titles) >= SEARCH_SOURCE_LIMIT:
            break
    return titles


def bounded_safe_text(value: object, max_chars: int) -> str:
    return sanitize_reasoning_text(str(value or ""), max_chars=max_chars)


def summarize_search_sources(result: dict[str, Any]) -> list[SearchSourceSummary]:
    items = result.get("results")
    if not isinstance(items, list):
        return []
    sources: list[SearchSourceSummary] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = bounded_safe_text(item.get("title") or "未命名结果", SEARCH_TITLE_CHARS)
        url = bounded_safe_text(item.get("url") or "", SEARCH_URL_CHARS)
        snippet = bounded_safe_text(
            item.get("content") or item.get("snippet") or "",
            SEARCH_SNIPPET_CHARS,
        )
        if not (title or url or snippet):
            continue
        sources.append(
            SearchSourceSummary(
                title=title or "未命名结果",
                url=url,
                snippet=snippet,
            )
        )
        if len(sources) >= SEARCH_SOURCE_LIMIT:
            break
    return sources


def build_search_synthesis_prompt(message: str, sources: list[SearchSourceSummary]) -> str:
    source_lines = "\n".join(
        (
            f"- 标题：{source.title}\n"
            f"  URL：{source.url or '无'}\n"
            f"  摘要：{source.snippet or '无'}"
        )
        for source in sources
    )
    safe_message = bounded_safe_text(message, 500)
    return (
        "你是 MyAgent 的联网检索结果合成器。请用中文直接回答用户问题，"
        "只依据下面的安全搜索摘要进行综合，不要输出原始 JSON，不要把工具结果逐条照抄为答案。"
        "如果信息不足，请明确说明不确定性，并列出关键来源。\n\n"
        f"用户问题：{safe_message}\n\n"
        f"安全搜索摘要：\n{source_lines}\n\n"
        "最终回答要求：先给结论，再给必要依据；保持简洁。"
    )


def render_search_fallback_answer(
    message: str,
    sources: list[SearchSourceSummary],
    warning: str,
) -> str:
    lines = [
        warning,
        "以下是联网检索返回的安全摘要，本轮没有读取历史上传文件，也没有启动文档分析：",
        "",
        f"问题：{bounded_safe_text(message, 240)}",
        "",
        "检索摘要：",
    ]
    for source in sources:
        source_line = f"- {source.title}"
        if source.snippet:
            source_line += f"：{source.snippet}"
        if source.url:
            source_line += f"（{source.url}）"
        lines.append(source_line)
    return "\n".join(lines)
