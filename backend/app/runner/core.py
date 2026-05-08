"""Task runner core: manages agent invocation lifecycle."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

from langchain_core.messages import HumanMessage

from app.agent.factory import build_agent
from app.config import Settings
from app.schemas import EventRecord
from app.storage import TaskStorage
from app.streaming.event_converter import convert_stream_event
from app.streaming.v2_adapter import stream_agent
from app.tools.registry import get_platform_tools

logger = logging.getLogger(__name__)


class TaskRunner:
    """Orchestrates agent execution for a task: build, stream, convert, collect."""

    def __init__(self, settings: Settings, storage: TaskStorage | None = None) -> None:
        self.settings = settings
        self.storage = storage
        self._active_runs: dict[str, asyncio.Task[None]] = {}

    async def start(
        self,
        task_id: str,
        message: str,
        *,
        model: str | None = None,
        run_id: str,
    ) -> list[EventRecord]:
        """Start an agent run for a task and collect all emitted events.

        Builds the agent, starts streaming, converts events via
        :func:`app.streaming.event_converter.convert_stream_event`, and returns
        the collected :class:`EventRecord` list.
        """
        model_id = model or self.settings.default_model

        task_workspace = self.settings.workspace_root / task_id
        tools = get_platform_tools(self.settings, task_workspace=task_workspace)

        agent = build_agent(
            self.settings,
            model=model_id,
            tools=tools,
            skills=list(self.settings.skills_dirs),
        )

        messages: list[Any] = [HumanMessage(content=message)]
        config: dict[str, Any] = {
            "configurable": {"thread_id": task_id},
        }

        collected: list[EventRecord] = []
        seq = 0

        try:
            async with asyncio.timeout(self.settings.agent_timeout_seconds):
                async for event in stream_agent(agent, messages, config=config):
                    record = convert_stream_event(event, task_id, run_id, seq=seq)
                    if record is not None:
                        collected.append(record)
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

        return collected

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
            try:
                collected = await self.start(task_id, message, model=model, run_id=run_id)
                for record in collected:
                    self.storage.append_event(
                        task_id,
                        record.type,
                        record.message,
                        record.payload,
                        run_id=record.run_id,
                        level=record.level,
                    )
                self.storage.update_task_if_status(task_id, {"running"}, status="complete", run_id=run_id)
            except TimeoutError:
                self.storage.update_task_if_status(
                    task_id,
                    {"running"},
                    status="failed",
                    error=f"运行超时（{self.settings.agent_timeout_seconds}秒）",
                    run_id=run_id,
                )
            except asyncio.CancelledError:
                self.storage.update_task_if_status(task_id, {"running"}, status="cancelled", run_id=run_id)
                raise
            except Exception as exc:
                self.storage.update_task_if_status(task_id, {"running"}, status="failed", error=str(exc), run_id=run_id)
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
