"""Task runner core: manages agent invocation lifecycle."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable
from typing import Any, Protocol

from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.factory import build_agent
from app.config import Settings
from app.contracts import EventLevel
from app.memory import AgentMemoryService, MemoryServiceError
from app.schemas import ChatMessage, EventRecord, TaskStatus
from app.streaming.event_converter import convert_stream_event
from app.streaming.v2_adapter import extract_final_answer, stream_agent
from app.tools.registry import get_platform_tools

logger = logging.getLogger(__name__)


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


class TaskRunner:
    """Orchestrates agent execution for a task: build, stream, convert, collect."""

    def __init__(
        self,
        settings: Settings,
        storage: RunnerStorage | None = None,
        memory_service: AgentMemoryService | None = None,
    ) -> None:
        self.settings = settings
        self.storage = storage
        self.memory_service = memory_service
        self._active_runs: dict[str, asyncio.Task[None]] = {}

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
        tools = get_platform_tools(self.settings)

        agent = build_agent(
            self.settings,
            model=model_id,
            tools=tools,
            skills=list(self.settings.skills_dirs),
            workspace_dir=task_workspace,
        )

        messages: list[Any] = []
        if self.memory_service is not None:
            memory_context = self.memory_service.recall_context(message)
            if memory_context:
                messages.append(SystemMessage(content=memory_context))
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
                        latest_state = event.get("data", {})
                    record = convert_stream_event(event, task_id, run_id, seq=seq)
                    if record is not None:
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
                collected.append(record)
                storage.append_event(
                    task_id,
                    record.type,
                    record.message,
                    record.payload,
                    run_id=record.run_id,
                    level=record.level,
                )

            try:
                collected, final_state = await self.start(
                    task_id, message, model=model, run_id=run_id, on_event=_append_event,
                )

                final_answer = extract_final_answer(final_state)

                append_message: ChatMessage | None = None
                if final_answer:
                    if self.memory_service is not None:
                        self.memory_service.remember_completed_run(
                            task_id=task_id,
                            run_id=run_id,
                            user_goal=message,
                            final_answer=final_answer,
                        )
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
                    event_payload={"previous_status": "running"},
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
                        payload={"content": final_answer},
                        run_id=run_id,
                        level="success",
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
                    event_payload={"error": error_message, "reason": "timeout"},
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
                    event_payload={"previous_status": "running"},
                    event_level="warning",
                )
                raise
            except MemoryServiceError as exc:
                self.storage.update_task_if_status_and_append_event(
                    task_id,
                    {"running"},
                    status="failed",
                    error=str(exc),
                    run_id=run_id,
                    event_type="task_failed",
                    event_message=str(exc),
                    event_payload={"error": str(exc), "source": "memory"},
                    event_level="error",
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
                    event_payload={"error": error_message},
                    event_level="error",
                )
                raise
            finally:
                self._active_runs.pop(task_id, None)

        self._active_runs[task_id] = asyncio.create_task(_run())

    async def cancel(self, task_id: str) -> None:
        """Cancel a running task."""
        task = self._active_runs.get(task_id)
        if task is None:
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        self._active_runs.pop(task_id, None)

    def is_running(self, task_id: str) -> bool:
        """Check if a task has an active run."""
        active = self._active_runs.get(task_id)
        return active is not None and not active.done()
