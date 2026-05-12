from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_get_models_preserves_available_flag(tmp_path):
    settings = Settings(
        task_root=tmp_path / "tasks",
        workspace_root=tmp_path / "tasks",
        deepseek_api_key="sk-test",
    )
    client = TestClient(create_app(settings))

    response = client.get("/api/models")

    assert response.status_code == 200
    models = response.json()
    deepseek = [model for model in models if model["provider"] == "deepseek"]
    openai = [model for model in models if model["provider"] == "openai"]
    assert deepseek
    assert all(model["available"] is True for model in deepseek)
    assert all(model["available"] is False for model in openai)

