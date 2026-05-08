"""Task runner core: manages agent invocation lifecycle."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from typing import Any

from langchain_core.messages import HumanMessage

from app.agent.factory import build_agent
from app.config import Settings
from app.schemas import EventRecord
from app.streaming.event_converter import convert_stream_event
from app.streaming.v2_adapter import stream_agent
from app.tools.registry import get_platform_tools

logger = logging.getLogger(__name__)


class TaskRunner:
    """Orchestrates agent execution for a task: build, stream, convert, collect."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._active_runs: dict[str, asyncio.Task[None]] = {}

    async def start(
        self,
        task_id: str,
        message: str,
        *,
        model: str | None = None,
    ) -> list[EventRecord]:
        """Start an agent run for a task and collect all emitted events.

        Builds the agent, starts streaming, converts events via
        :func:`app.streaming.event_converter.convert_stream_event`, and returns
        the collected :class:`EventRecord` list.
        """
        run_id = str(uuid.uuid4())
        model_id = model or self.settings.default_model

        agent = build_agent(
            self.settings,
            model=model_id,
            tools=get_platform_tools(self.settings),
            skills=list(self.settings.skills_dirs),
        )

        messages: list[Any] = [HumanMessage(content=message)]
        config: dict[str, Any] = {
            "configurable": {"thread_id": task_id},
        }

        collected: list[EventRecord] = []
        seq = 0

        try:
            async for event in stream_agent(agent, messages, config=config):
                record = convert_stream_event(event, task_id, run_id, seq=seq)
                if record is not None:
                    collected.append(record)
                    seq += 1
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
    ) -> None:
        """Fire-and-forget start — runs :meth:`start` in a managed ``asyncio.Task``."""
        if task_id in self._active_runs:
            raise RuntimeError(f"Task {task_id} already has an active run")

        async def _run() -> None:
            try:
                await self.start(task_id, message, model=model)
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
