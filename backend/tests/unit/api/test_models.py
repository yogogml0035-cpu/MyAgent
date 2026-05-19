from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_get_models_returns_only_deepseek_v4_flash_options(tmp_path):
    settings = Settings(
        task_root=tmp_path / "tasks",
        workspace_root=tmp_path / "tasks",
        deepseek_api_key="sk-test",
    )
    client = TestClient(create_app(settings))

    response = client.get("/api/models")

    assert response.status_code == 200
    models = response.json()
    assert [model["id"] for model in models] == [
        "deepseek-v4-flash",
        "deepseek-v4-flash-thinking",
    ]
    assert all(model["provider"] == "deepseek" for model in models)
    assert all(model["available"] is True for model in models)
