from __future__ import annotations

from pathlib import Path

import app.settings as settings_module


def test_load_settings_defaults_task_root_to_storage_sessions(monkeypatch) -> None:
    monkeypatch.delenv("MYAGENT_TASK_ROOT", raising=False)
    monkeypatch.delenv("AGENT_CHAT_TASK_ROOT", raising=False)
    monkeypatch.setattr(settings_module, "load_env_file", lambda path: None)

    settings = settings_module.load_settings()
    backend_root = Path(settings_module.__file__).resolve().parents[1]

    assert settings.task_root == (backend_root / "storage" / "sessions").resolve()
    assert settings.workspace_root == settings.task_root
