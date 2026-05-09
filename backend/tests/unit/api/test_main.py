from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

BACKEND_ROOT = Path(__file__).resolve().parents[3]


def test_import_app_main_suppresses_startup_deprecation_warnings():
    result = subprocess.run(
        [sys.executable, "-Walways", "-c", "import app.main"],
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    combined_output = f"{result.stdout}\n{result.stderr}"

    assert result.returncode == 0, combined_output
    assert "LangChainPendingDeprecationWarning" not in combined_output
    assert "default value of `allowed_objects`" not in combined_output
    assert "on_event is deprecated" not in combined_output


def test_lifespan_interrupts_running_tasks_on_startup(tmp_path, monkeypatch):
    settings = Settings(
        task_root=tmp_path / "tasks",
        workspace_root=tmp_path / "tasks",
    )
    app = create_app(settings)
    storage = app.state.storage
    calls: list[str] = []

    original_interrupt = storage.interrupt_running_tasks

    def record_interrupt(reason: str) -> list[str]:
        calls.append(reason)
        return original_interrupt(reason)

    monkeypatch.setattr(storage, "interrupt_running_tasks", record_interrupt)

    with TestClient(app):
        pass

    assert calls == ["后端启动或重载时中断了任务。"]
