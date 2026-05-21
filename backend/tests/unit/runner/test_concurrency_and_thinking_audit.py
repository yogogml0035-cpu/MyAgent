from __future__ import annotations

import asyncio
from collections.abc import Callable

import pytest
from langchain_core.messages import AIMessage

from app.runner.core import TaskRunner
from tests.fakes import InMemoryTaskStorage


async def _wait_for(predicate: Callable[[], bool], *, timeout: float = 1.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("condition was not met before timeout")


class TestConcurrencyAndThinkingAudit:
    @pytest.mark.asyncio
    async def test_different_tasks_can_run_concurrently(self, test_settings, monkeypatch):
        storage = InMemoryTaskStorage(test_settings.task_root)
        runner = TaskRunner(test_settings, storage)

        task_a = storage.create_task(message=None, model="deepseek-v4-flash")
        task_b = storage.create_task(message=None, model="deepseek-v4-flash")
        run_result_a = storage.start_run(
            task_a.task_id,
            message="task a",
            model="deepseek-v4-flash",
            expected_statuses={"idle"},
        )
        run_result_b = storage.start_run(
            task_b.task_id,
            message="task b",
            model="deepseek-v4-flash",
            expected_statuses={"idle"},
        )
        assert run_result_a is not None
        assert run_result_b is not None
        _, run_id_a = run_result_a
        _, run_id_b = run_result_b

        releases = {
            task_a.task_id: asyncio.Event(),
            task_b.task_id: asyncio.Event(),
        }
        started: set[str] = set()
        both_started = asyncio.Event()

        async def fake_start(task_id: str, message: str, *, model: str | None, run_id: str, on_event=None):
            del message, model, run_id, on_event
            started.add(task_id)
            if len(started) == 2:
                both_started.set()
            await releases[task_id].wait()
            return [], {"messages": [AIMessage(content=f"done-{task_id}")]}

        monkeypatch.setattr(runner, "start", fake_start)

        runner.start_background(task_a.task_id, "task a", model="deepseek-v4-flash", run_id=run_id_a)
        runner.start_background(task_b.task_id, "task b", model="deepseek-v4-flash", run_id=run_id_b)

        try:
            await asyncio.wait_for(both_started.wait(), timeout=1.0)

            assert runner.is_running(task_a.task_id)
            assert runner.is_running(task_b.task_id)
            assert set(runner._active_runs) == {task_a.task_id, task_b.task_id}

            state_a = storage.get_task(task_a.task_id)
            state_b = storage.get_task(task_b.task_id)
            assert state_a.status == "running"
            assert state_b.status == "running"
            assert state_a.active_run_id == run_id_a
            assert state_b.active_run_id == run_id_b
        finally:
            releases[task_a.task_id].set()
            releases[task_b.task_id].set()
            await _wait_for(
                lambda: not runner.is_running(task_a.task_id)
                and not runner.is_running(task_b.task_id)
            )

        assert storage.get_task(task_a.task_id).status == "complete"
        assert storage.get_task(task_b.task_id).status == "complete"

    @pytest.mark.asyncio
    async def test_failed_task_does_not_change_other_task_active_run(self, test_settings, monkeypatch):
        storage = InMemoryTaskStorage(test_settings.task_root)
        runner = TaskRunner(test_settings, storage)

        task_a = storage.create_task(message=None, model="deepseek-v4-flash")
        task_b = storage.create_task(message=None, model="deepseek-v4-flash")
        run_result_a = storage.start_run(
            task_a.task_id,
            message="task a",
            model="deepseek-v4-flash",
            expected_statuses={"idle"},
        )
        run_result_b = storage.start_run(
            task_b.task_id,
            message="task b",
            model="deepseek-v4-flash",
            expected_statuses={"idle"},
        )
        assert run_result_a is not None
        assert run_result_b is not None
        _, run_id_a = run_result_a
        _, run_id_b = run_result_b

        allow_a_failure = asyncio.Event()
        release_b = asyncio.Event()
        started_a = asyncio.Event()
        started_b = asyncio.Event()

        async def fake_start(task_id: str, message: str, *, model: str | None, run_id: str, on_event=None):
            del message, model, run_id, on_event
            if task_id == task_a.task_id:
                started_a.set()
                await allow_a_failure.wait()
                raise RuntimeError("task-a boom")
            started_b.set()
            await release_b.wait()
            return [], {"messages": [AIMessage(content="done-b")]}

        monkeypatch.setattr(runner, "start", fake_start)

        runner.start_background(task_a.task_id, "task a", model="deepseek-v4-flash", run_id=run_id_a)
        runner.start_background(task_b.task_id, "task b", model="deepseek-v4-flash", run_id=run_id_b)

        try:
            await asyncio.wait_for(started_a.wait(), timeout=1.0)
            await asyncio.wait_for(started_b.wait(), timeout=1.0)

            allow_a_failure.set()
            await _wait_for(lambda: storage.get_task(task_a.task_id).status == "failed")

            state_a = storage.get_task(task_a.task_id)
            state_b = storage.get_task(task_b.task_id)
            assert state_a.active_run_id is None
            assert state_b.status == "running"
            assert state_b.active_run_id == run_id_b
            assert runner.is_running(task_b.task_id)

            failed_events = [
                event for event in storage.read_events(task_a.task_id) if event.type == "task_failed"
            ]
            assert len(failed_events) == 1
            assert failed_events[0].run_id == run_id_a
            assert not any(
                event.type == "task_failed" for event in storage.read_events(task_b.task_id)
            )
        finally:
            allow_a_failure.set()
            release_b.set()
            await _wait_for(
                lambda: not runner.is_running(task_a.task_id)
                and not runner.is_running(task_b.task_id)
            )

        assert storage.get_task(task_b.task_id).status == "complete"
