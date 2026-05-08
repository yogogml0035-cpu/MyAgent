from __future__ import annotations

import inspect

from app.runner.core import TaskRunner


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
