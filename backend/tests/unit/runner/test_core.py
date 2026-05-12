from __future__ import annotations

import asyncio
import inspect

import pytest
from langchain_core.messages import AIMessage

from app.runner.core import TaskRunner
from app.storage import TaskStorage


class TestTaskRunnerInit:
    def test_init_stores_settings(self, test_settings):
        runner = TaskRunner(test_settings)
        assert runner.settings is test_settings

    def test_has_start_method(self):
        sig = inspect.signature(TaskRunner.start)
        params = list(sig.parameters)
        assert "task_id" in params
        assert "message" in params

    def test_has_cancel_method(self):
        sig = inspect.signature(TaskRunner.cancel)
        params = list(sig.parameters)
        assert "task_id" in params

    def test_has_is_running_method(self):
        assert hasattr(TaskRunner, "is_running")

    def test_no_active_runs_after_init(self, test_settings):
        runner = TaskRunner(test_settings)
        assert runner._active_runs == {}


async def _wait_for_runner(runner: TaskRunner, task_id: str) -> None:
    for _ in range(50):
        if not runner.is_running(task_id):
            return
        await asyncio.sleep(0.01)
    raise AssertionError("runner did not finish")


class TestTaskRunnerTerminalEvents:
    @pytest.mark.asyncio
    async def test_successful_background_run_writes_task_completed_event(
        self, test_settings, monkeypatch
    ):
        storage = TaskStorage(test_settings.task_root)
        runner = TaskRunner(test_settings, storage)
        state = storage.create_task(message=None, model="deepseek:deepseek-chat")
        run_result = storage.start_run(
            state.task_id,
            message="hello",
            model="deepseek:deepseek-chat",
            expected_statuses={"idle"},
        )
        assert run_result is not None
        _, run_id = run_result

        async def fake_start(*args, **kwargs):
            return [], {"messages": [AIMessage(content="done")]}

        monkeypatch.setattr(runner, "start", fake_start)

        runner.start_background(state.task_id, "hello", model="deepseek:deepseek-chat", run_id=run_id)
        await _wait_for_runner(runner, state.task_id)

        events = storage.read_events(state.task_id)
        completed = [event for event in events if event.type == "task_completed"]
        final_answers = [event for event in events if event.type == "final_answer"]

        assert len(completed) == 1
        assert completed[0].run_id == run_id
        assert completed[0].level == "success"
        assert len(final_answers) == 1
        assert final_answers[0].run_id == run_id

    @pytest.mark.asyncio
    async def test_failed_background_run_writes_task_failed_event(
        self, test_settings, monkeypatch
    ):
        storage = TaskStorage(test_settings.task_root)
        runner = TaskRunner(test_settings, storage)
        state = storage.create_task(message=None, model="deepseek:deepseek-chat")
        run_result = storage.start_run(
            state.task_id,
            message="hello",
            model="deepseek:deepseek-chat",
            expected_statuses={"idle"},
        )
        assert run_result is not None
        _, run_id = run_result

        async def fake_start(*args, **kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(runner, "start", fake_start)

        runner.start_background(state.task_id, "hello", model="deepseek:deepseek-chat", run_id=run_id)
        await _wait_for_runner(runner, state.task_id)

        failed = [event for event in storage.read_events(state.task_id) if event.type == "task_failed"]

        assert len(failed) == 1
        assert failed[0].run_id == run_id
        assert failed[0].payload["error"] == "boom"
        assert storage.get_task(state.task_id).status == "failed"

    @pytest.mark.asyncio
    async def test_cancelled_background_run_writes_run_scoped_cancel_event(
        self, test_settings, monkeypatch
    ):
        storage = TaskStorage(test_settings.task_root)
        runner = TaskRunner(test_settings, storage)
        state = storage.create_task(message=None, model="deepseek:deepseek-chat")
        run_result = storage.start_run(
            state.task_id,
            message="hello",
            model="deepseek:deepseek-chat",
            expected_statuses={"idle"},
        )
        assert run_result is not None
        _, run_id = run_result

        async def fake_start(*args, **kwargs):
            await asyncio.sleep(60)
            return [], {}

        monkeypatch.setattr(runner, "start", fake_start)

        runner.start_background(state.task_id, "hello", model="deepseek:deepseek-chat", run_id=run_id)
        await asyncio.sleep(0)
        await runner.cancel(state.task_id)

        cancelled = [
            event for event in storage.read_events(state.task_id) if event.type == "task_cancelled"
        ]

        assert len(cancelled) == 1
        assert cancelled[0].run_id == run_id
        assert storage.get_task(state.task_id).status == "cancelled"
