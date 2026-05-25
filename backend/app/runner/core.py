"""Task runner core: manages agent invocation lifecycle."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import logging
import re
from collections.abc import Callable
from typing import Any, Protocol

from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.factory import build_agent
from app.agent_store import PostgresAgentStore
from app.config import Settings
from app.contracts import EventLevel
from app.conversation_context import ConversationContextBuilder
from app.execution.resources import (
    RESOURCE_TOOL_READ_ONLY_SYSTEM_PROMPT,
    RESOURCE_TOOL_SYSTEM_PROMPT,
    build_resource_manifest,
    format_resource_manifest_message,
)
from app.schemas import ChatMessage, EventRecord, TaskStatus
from app.streaming.event_converter import convert_stream_event
from app.streaming.v2_adapter import extract_final_answer, stream_agent
from app.tools.registry import get_platform_tools

logger = logging.getLogger(__name__)

DELIVERABLE_REQUEST_PATTERNS: tuple[tuple[str, str], ...] = (
    ("word", r"(生成|导出|输出|交付|提供|整理|保存).{0,24}(word|docx|文档)"),
    ("powerpoint", r"(生成|导出|输出|交付|提供|整理|保存).{0,24}(ppt|pptx|幻灯片)"),
    ("excel", r"(生成|导出|输出|交付|提供|整理|保存).{0,24}(excel|xlsx|xlsm|表格)"),
    ("report", r"(生成|导出|输出|交付|提供|整理|保存).{0,24}(报告|report|pdf|html)"),
)
SOURCE_DEPENDENT_REQUEST_PATTERN = re.compile(
    r"(总结|汇总|概括|摘要|提炼|归纳|梳理|分析|阅读|整理|summari[sz]e|summary|analy[sz]e)",
    re.IGNORECASE,
)
INLINE_SOURCE_MIN_CHARS = 24
WEB_RESEARCH_SKILL_REF = "[$web-research]"
WEB_RESEARCH_MAX_SEARCH_CALLS = 5
WEB_RESEARCH_RUNTIME_SYSTEM_PROMPT = f"""当前消息选择了 web-research 技能，按快速联网核查模式执行。
- 总搜索调用不超过 {WEB_RESEARCH_MAX_SEARCH_CALLS} 次，每次 max_results 不超过 5。
- 先读取必要的上传资源，提取关键参数，再只做针对性搜索。
- 不要使用 task/sub-agent 委派，不要为简单联网核查创建 Word、PPT、Excel 或报告产物，除非用户明确要求可下载文件。
- 搜到足够证据后立即综合回答；如果搜索引擎返回验证码、502、无关结果或证据不足，说明不确定性并结束，不要继续扩展搜索。"""


class RunnerStorage(Protocol):
    def append_event(
        self,
        task_id: str,
        event_type: str,
        message: str,
        payload: dict[str, Any] | None = None,
        *,
        run_id: str | None = None,
        level: EventLevel | None = None,
    ) -> EventRecord: ...

    def get_task(self, task_id: str, *, include_events: bool = True) -> Any: ...

    def update_task_if_status_and_append_event(
        self,
        task_id: str,
        expected_statuses: set[TaskStatus],
        *,
        event_type: str,
        event_message: str,
        event_payload: dict[str, Any] | None = None,
        event_level: EventLevel | None = None,
        status: TaskStatus | None = None,
        error: str | None = None,
        needs_input: dict[str, Any] | None = None,
        append_message: ChatMessage | None = None,
        run_id: str | None = None,
        artifact_names: list[str] | None = None,
    ) -> Any: ...


class RunnerMemoryService(Protocol):
    def recall_context(
        self, user_message: str, *, user_id: str | None = None, limit: int = 3
    ) -> str | None: ...

    def recall_event_payload(
        self, context: str | None, *, user_id: str | None = None
    ) -> dict[str, Any] | None: ...

    def remember_completed_run(
        self,
        *,
        task_id: str,
        run_id: str,
        user_goal: str,
        final_answer: str,
        user_id: str | None = None,
        model: str | None = None,
    ) -> None: ...


class TaskRunner:
    """Orchestrates agent execution for a task: build, stream, convert, collect."""

    def __init__(
        self,
        settings: Settings,
        storage: RunnerStorage | None = None,
        memory_service: Any | None = None,
        context_builder: ConversationContextBuilder | None = None,
        agent_store: PostgresAgentStore | None = None,
    ) -> None:
        self.settings = settings
        self.storage = storage
        self.memory_service = memory_service
        self.context_builder = context_builder
        self.agent_store = agent_store
        self._active_runs: dict[str, asyncio.Task[None]] = {}
        self._active_run_ids: dict[str, str] = {}
        self._cancel_requested_run_ids: set[str] = set()
        self._memory_tasks: set[asyncio.Task[None]] = set()

    async def start(
        self,
        task_id: str,
        message: str,
        *,
        model: str | None = None,
        run_id: str,
        on_event: Callable[[EventRecord], None] | None = None,
    ) -> tuple[list[EventRecord], dict[str, Any]]:
        """Start an agent run for a task and collect all emitted events.

        Builds the agent, starts streaming, converts events via
        :func:`app.streaming.event_converter.convert_stream_event`, and returns
        the collected :class:`EventRecord` list and the latest graph state dict.
        """
        model_id = model or self.settings.default_model

        task_workspace = self.settings.workspace_root / task_id
        task_workspace.mkdir(parents=True, exist_ok=True)
        web_research_mode = _is_web_research_message(message)
        include_artifact_tools = _should_include_artifact_tools(message)
        tools = get_platform_tools(
            self.settings,
            task_id=task_id,
            run_id=run_id,
            storage=self.storage,
            include_artifact_tools=include_artifact_tools,
            searxng_max_calls_per_run=(
                WEB_RESEARCH_MAX_SEARCH_CALLS if web_research_mode else None
            ),
        )

        agent = build_agent(
            self.settings,
            model=model_id,
            tools=tools,
            system_prompt=_runner_system_prompt(
                web_research_mode=web_research_mode,
                include_artifact_tools=include_artifact_tools,
            ),
            skills=list(self.settings.skills_dirs),
            workspace_dir=task_workspace,
            store=self.agent_store,
        )

        messages: list[Any] = []
        if self.context_builder is not None:
            context = await asyncio.to_thread(
                self.context_builder.build,
                task_id=task_id,
                current_message=message,
            )
            if context.loaded:
                context_event = _make_runner_event(
                    task_id,
                    run_id,
                    "context_loaded",
                    "已载入会话上下文。",
                    context.event_payload(),
                    level="info",
                    seq=-2,
                )
                if on_event is not None:
                    on_event(context_event)
                messages.extend(context.messages)
        memory_context = await self._recall_memory_context(message)
        if memory_context:
            messages.append(SystemMessage(content=memory_context))
            memory_event_payload = self._memory_recall_event_payload(memory_context)
            if memory_event_payload and on_event is not None:
                on_event(
                    _make_runner_event(
                        task_id,
                        run_id,
                        "memory_recalled",
                        "已载入长期记忆。",
                        memory_event_payload,
                        level="info",
                        seq=-1,
                    )
                )
        resource_message = self._resource_manifest_context(
            task_id,
            include_artifact_tools=include_artifact_tools,
        )
        if resource_message:
            messages.append(SystemMessage(content=resource_message))
        messages.append(HumanMessage(content=message))
        config: dict[str, Any] = {
            "configurable": {"thread_id": task_id},
        }

        collected: list[EventRecord] = []
        latest_state: dict[str, Any] = {}
        seq = 0

        try:
            async with asyncio.timeout(self.settings.agent_timeout_seconds):
                async for event in stream_agent(agent, messages, config=config):
                    if event.get("type") == "values_snapshot":
                        data = event.get("data")
                        if isinstance(data, dict) and not data.get("is_subgraph", False):
                            latest_state = data
                    record = convert_stream_event(event, task_id, run_id, seq=seq)
                    if record is not None:
                        record = _bind_event_to_run(record, run_id)
                        collected.append(record)
                        if on_event is not None:
                            on_event(record)
                        seq += 1
        except TimeoutError:
            logger.warning(
                "Run %s for task %s timed out after %.1fs",
                run_id, task_id, self.settings.agent_timeout_seconds,
            )
            raise
        except asyncio.CancelledError:
            logger.info("Run %s for task %s was cancelled", run_id, task_id)
            raise
        except Exception:
            logger.exception("Run %s for task %s failed", run_id, task_id)
            raise

        return collected, latest_state

    def start_background(
        self,
        task_id: str,
        message: str,
        *,
        model: str | None = None,
        run_id: str,
    ) -> None:
        """Fire-and-forget start — runs :meth:`start` in a managed ``asyncio.Task``."""
        if task_id in self._active_runs:
            raise RuntimeError(f"Task {task_id} already has an active run")

        async def _run() -> None:
            assert self.storage is not None
            storage = self.storage
            collected: list[EventRecord] = []
            final_state: dict[str, Any] = {}

            def _append_event(record: EventRecord) -> None:
                if run_id in self._cancel_requested_run_ids:
                    raise asyncio.CancelledError
                scoped_record = _bind_event_to_run(record, run_id)
                collected.append(scoped_record)
                storage.append_event(
                    task_id,
                    scoped_record.type,
                    scoped_record.message,
                    scoped_record.payload,
                    run_id=scoped_record.run_id,
                    level=scoped_record.level,
                )

            try:
                missing_source_clarification = self._missing_source_input_clarification(
                    task_id=task_id,
                    run_id=run_id,
                    user_message=message,
                )
                if missing_source_clarification is not None:
                    clarification_message = ChatMessage(
                        role="assistant",
                        content=missing_source_clarification,
                        created_at="",
                        run_id=run_id,
                    )
                    self.storage.update_task_if_status_and_append_event(
                        task_id,
                        {"running"},
                        status="complete",
                        run_id=run_id,
                        append_message=clarification_message,
                        event_type="task_completed",
                        event_message="已请求补充文件或内容。",
                        event_payload=_terminal_event_payload(
                            "已请求补充文件或内容",
                            stage="completed",
                            previous_status="running",
                        ),
                        event_level="success",
                    )
                    storage.append_event(
                        task_id,
                        "final_answer",
                        "Final answer generated",
                        payload={
                            "content": missing_source_clarification,
                            "live": _answer_completed_live_metadata(),
                        },
                        run_id=run_id,
                        level="success",
                    )
                    return

                collected, final_state = await self.start(
                    task_id, message, model=model, run_id=run_id, on_event=_append_event,
                )

                final_answer = extract_final_answer(final_state)
                append_message: ChatMessage | None = None
                if final_answer:
                    append_message = ChatMessage(
                        role="assistant",
                        content=final_answer,
                        created_at="",
                        run_id=run_id,
                    )

                self.storage.update_task_if_status_and_append_event(
                    task_id,
                    {"running"},
                    status="complete",
                    run_id=run_id,
                    append_message=append_message,
                    event_type="task_completed",
                    event_message="任务已完成。",
                    event_payload=_terminal_event_payload(
                        "任务已完成",
                        stage="completed",
                        previous_status="running",
                    ),
                    event_level="success",
                )

                # Emit a synthetic final_answer event so the frontend can
                # refresh immediately and display the authoritative answer
                # extracted from final_state (not the intermediate deltas).
                if final_answer:
                    storage.append_event(
                        task_id,
                        "final_answer",
                        "Final answer generated",
                        payload={
                            "content": final_answer,
                            "live": _answer_completed_live_metadata(),
                        },
                        run_id=run_id,
                        level="success",
                    )
                    self._schedule_completed_run_memory_write(
                        task_id=task_id,
                        run_id=run_id,
                        user_goal=message,
                        final_answer=final_answer,
                        model=model,
                    )
            except TimeoutError:
                error_message = f"运行超时（{self.settings.agent_timeout_seconds}秒）"
                self.storage.update_task_if_status_and_append_event(
                    task_id,
                    {"running"},
                    status="failed",
                    error=error_message,
                    run_id=run_id,
                    event_type="task_failed",
                    event_message=error_message,
                    event_payload=_terminal_event_payload(
                        "任务失败",
                        stage="failed",
                        error=error_message,
                        reason="timeout",
                    ),
                    event_level="error",
                )
            except asyncio.CancelledError:
                self.storage.update_task_if_status_and_append_event(
                    task_id,
                    {"running"},
                    status="cancelled",
                    run_id=run_id,
                    event_type="task_cancelled",
                    event_message="任务已取消。",
                    event_payload=_terminal_event_payload(
                        "任务已取消",
                        stage="completed",
                        result_status="cancelled",
                        previous_status="running",
                    ),
                    event_level="warning",
                )
                raise
            except Exception as exc:
                error_message = str(exc)
                self.storage.update_task_if_status_and_append_event(
                    task_id,
                    {"running"},
                    status="failed",
                    error=error_message,
                    run_id=run_id,
                    event_type="task_failed",
                    event_message=error_message,
                    event_payload=_terminal_event_payload(
                        "任务失败",
                        stage="failed",
                        error=error_message,
                    ),
                    event_level="error",
                )
                raise
            finally:
                self._active_runs.pop(task_id, None)
                self._active_run_ids.pop(task_id, None)
                self._cancel_requested_run_ids.discard(run_id)

        self._active_runs[task_id] = asyncio.create_task(_run())
        self._active_run_ids[task_id] = run_id

    async def _recall_memory_context(self, message: str) -> str | None:
        memory_service = self.memory_service
        if memory_service is None:
            return None
        try:
            return await asyncio.to_thread(
                _call_memory_recall,
                memory_service,
                message,
                self.settings.default_user_id,
            )
        except Exception:
            logger.warning("Long-term memory recall failed; continuing without memory", exc_info=True)
            return None

    def _memory_recall_event_payload(self, memory_context: str | None) -> dict[str, Any] | None:
        memory_service = self.memory_service
        if memory_service is None:
            return None
        try:
            return memory_service.recall_event_payload(
                memory_context,
                user_id=self.settings.default_user_id,
            )
        except Exception:
            logger.warning("Long-term memory recall event payload failed", exc_info=True)
            return None

    def _resource_manifest_context(
        self,
        task_id: str,
        *,
        include_artifact_tools: bool = True,
    ) -> str:
        try:
            manifest = build_resource_manifest(task_id, self.settings.workspace_root)
        except Exception:
            logger.warning("Resource manifest provisioning failed; continuing without it", exc_info=True)
            return ""
        return format_resource_manifest_message(
            manifest,
            include_artifact_tools=include_artifact_tools,
        )

    def _schedule_completed_run_memory_write(
        self,
        *,
        task_id: str,
        run_id: str,
        user_goal: str,
        final_answer: str,
        model: str | None = None,
    ) -> None:
        memory_service = self.memory_service
        if memory_service is None:
            return

        async def _remember() -> None:
            try:
                await asyncio.to_thread(
                    _call_memory_remember,
                    memory_service,
                    task_id,
                    run_id,
                    user_goal,
                    final_answer,
                    self.settings.default_user_id,
                    model,
                )
            except Exception:
                logger.warning(
                    "Long-term memory write failed after successful run; keeping task complete",
                    exc_info=True,
                )

        task = asyncio.create_task(_remember())
        self._memory_tasks.add(task)
        task.add_done_callback(self._memory_tasks.discard)

    async def cancel(self, task_id: str) -> None:
        """Cancel a running task."""
        task = self._active_runs.get(task_id)
        if task is None:
            return
        self.request_cancel(task_id)
        with contextlib.suppress(asyncio.CancelledError):
            await task
        self._active_runs.pop(task_id, None)
        self._active_run_ids.pop(task_id, None)

    def request_cancel(self, task_id: str) -> str | None:
        """Request cancellation and return the active run id without waiting."""
        task = self._active_runs.get(task_id)
        if task is None or task.done():
            return None
        run_id = self._active_run_ids.get(task_id)
        if run_id:
            self._cancel_requested_run_ids.add(run_id)
        task.cancel()
        self._active_runs.pop(task_id, None)
        self._active_run_ids.pop(task_id, None)
        return run_id

    def is_running(self, task_id: str) -> bool:
        """Check if a task has an active run."""
        active = self._active_runs.get(task_id)
        return active is not None and not active.done()

    def _missing_source_input_clarification(
        self,
        *,
        task_id: str,
        run_id: str,
        user_message: str,
    ) -> str | None:
        storage = self.storage
        if storage is None or not _requests_source_dependent_work(user_message):
            return None

        try:
            state = storage.get_task(task_id, include_events=False)
        except Exception:
            logger.warning(
                "Unable to inspect task %s before missing-source clarification", task_id, exc_info=True
            )
            return None

        if state.upload_count > 0:
            return None
        if _message_contains_inline_source_text(user_message):
            return None
        if _has_reusable_source_context(state.messages, current_run_id=run_id):
            return None
        if _has_context_summary(storage, task_id):
            return None

        deliverable_kinds = _requested_deliverable_kinds(user_message)
        if deliverable_kinds:
            kind_label = _humanize_deliverable_kind(sorted(deliverable_kinds)[0])
            return f"你是不是忘记上传文件了？上传后我继续帮你生成 {kind_label}。"
        return "你是不是忘记上传文件或粘贴要处理的内容了？补充后我继续帮你总结。"


def _make_runner_event(
    task_id: str,
    run_id: str,
    event_type: str,
    message: str,
    payload: dict[str, Any],
    *,
    level: EventLevel = "info",
    seq: int | None = None,
) -> EventRecord:
    import uuid
    from datetime import datetime, timezone

    return EventRecord(
        id=str(uuid.uuid4()),
        session_id=task_id,
        seq=seq,
        type=event_type,
        message=message,
        created_at=datetime.now(timezone.utc).isoformat(),
        payload=payload,
        run_id=run_id,
        level=level,
    )


def _is_web_research_message(message: str) -> bool:
    return WEB_RESEARCH_SKILL_REF in message


def _should_include_artifact_tools(message: str) -> bool:
    if not _is_web_research_message(message):
        return True
    return bool(_requested_deliverable_kinds(message))


def _runner_system_prompt(
    *,
    web_research_mode: bool,
    include_artifact_tools: bool,
) -> str:
    resource_prompt = (
        RESOURCE_TOOL_SYSTEM_PROMPT
        if include_artifact_tools
        else RESOURCE_TOOL_READ_ONLY_SYSTEM_PROMPT
    )
    if not web_research_mode:
        return resource_prompt
    return f"{WEB_RESEARCH_RUNTIME_SYSTEM_PROMPT}\n\n{resource_prompt}"


def _bind_event_to_run(record: EventRecord, run_id: str) -> EventRecord:
    if record.run_id == run_id:
        return record
    return record.model_copy(update={"run_id": run_id})


def _terminal_event_payload(
    display_text: str,
    *,
    stage: str,
    result_status: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    payload = {**extra}
    live = {
        "schema_version": 1,
        "kind": "status",
        "stage": stage,
        "display_text": display_text,
        "diagnostic_label": "runner.terminal",
        "parameter_items": _terminal_parameter_items(extra),
    }
    if result_status:
        live["result_status"] = result_status
    payload["live"] = live
    return payload


def _answer_completed_live_metadata() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "answer_status",
        "stage": "completed",
        "display_text": "回答已完成",
        "diagnostic_label": "runner.final_answer",
        "parameter_items": [],
        "result_status": "success",
    }


def _terminal_parameter_items(extra: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for key in ("previous_status", "reason"):
        value = extra.get(key)
        if isinstance(value, (str, int, float, bool)):
            items.append({"key": key, "value": value})
    return items


def _requested_deliverable_kinds(message: str) -> set[str]:
    normalized = " ".join(message.split()).casefold()
    requested: set[str] = set()
    for kind, pattern in DELIVERABLE_REQUEST_PATTERNS:
        if re.search(pattern, normalized, re.IGNORECASE):
            requested.add(kind)
    return requested


def _requests_source_dependent_work(message: str) -> bool:
    if _requested_deliverable_kinds(message):
        return True
    return SOURCE_DEPENDENT_REQUEST_PATTERN.search(message) is not None


def _message_contains_inline_source_text(message: str) -> bool:
    normalized = " ".join(message.split())
    if len(_source_signal_text(normalized)) >= 80:
        return True
    for separator in ("\n", "：", ":"):
        if separator not in message:
            continue
        tail = message.rsplit(separator, 1)[-1]
        if len(_source_signal_text(tail)) >= INLINE_SOURCE_MIN_CHARS:
            return True
    return False


def _has_reusable_source_context(messages: list[ChatMessage], *, current_run_id: str) -> bool:
    for message in messages:
        if message.run_id == current_run_id:
            continue
        content = message.content.strip()
        if not content:
            continue
        if message.role == "user":
            if _message_contains_inline_source_text(content):
                return True
            if not _requests_source_dependent_work(content) and len(_source_signal_text(content)) >= 40:
                return True
        elif message.role == "assistant":
            if "忘记上传文件" in content:
                continue
            if len(_source_signal_text(content)) >= 120:
                return True
    return False


def _source_signal_text(text: str) -> str:
    without_common_request_terms = re.sub(
        r"(请|帮我|帮忙|总结|汇总|概括|摘要|提炼|归纳|梳理|分析|阅读|整理|生成|导出|输出|交付|提供|保存|"
        r"word|docx|ppt|pptx|excel|xlsx|xlsm|报告|文档|文件|内容|材料|资料|文本|一下|一个|一份|给我)",
        "",
        text,
        flags=re.IGNORECASE,
    )
    return "".join(ch for ch in without_common_request_terms if ch.isalnum())


def _has_context_summary(storage: RunnerStorage, task_id: str) -> bool:
    get_context_summary = getattr(storage, "get_context_summary", None)
    if not callable(get_context_summary):
        return False
    try:
        summary = get_context_summary(task_id)
    except Exception:
        logger.warning("Unable to inspect task %s context summary", task_id, exc_info=True)
        return False
    return bool(str(summary or "").strip())


def _humanize_deliverable_kind(kind: str) -> str:
    if kind == "word":
        return "Word"
    if kind == "powerpoint":
        return "PPT"
    if kind == "excel":
        return "Excel"
    if kind == "report":
        return "报告"
    return kind


def _call_memory_recall(memory_service: Any, message: str, user_id: str) -> str | None:
    signature = inspect.signature(memory_service.recall_context)
    if "user_id" in signature.parameters:
        return memory_service.recall_context(message, user_id=user_id)
    return memory_service.recall_context(message)


def _call_memory_remember(
    memory_service: Any,
    task_id: str,
    run_id: str,
    user_goal: str,
    final_answer: str,
    user_id: str,
    model: str | None,
) -> Any:
    signature = inspect.signature(memory_service.remember_completed_run)
    kwargs: dict[str, Any] = {
        "task_id": task_id,
        "run_id": run_id,
        "user_goal": user_goal,
        "final_answer": final_answer,
    }
    if "user_id" in signature.parameters:
        kwargs["user_id"] = user_id
    if "model" in signature.parameters:
        kwargs["model"] = model
    return memory_service.remember_completed_run(**kwargs)
