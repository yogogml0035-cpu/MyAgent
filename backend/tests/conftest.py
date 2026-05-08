"""Shared test fixtures for MyAgent backend."""
from __future__ import annotations

import pytest

from app.config import Settings


@pytest.fixture
def test_settings(tmp_path):
    """Provide a Settings instance with temporary paths and no real API keys."""
    return Settings(
        task_root=tmp_path / "tasks",
        workspace_root=tmp_path / "tasks",
    )
