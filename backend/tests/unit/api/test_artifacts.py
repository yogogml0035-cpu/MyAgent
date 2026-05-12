from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def _client(tmp_path):
    settings = Settings(
        task_root=tmp_path / "tasks",
        workspace_root=tmp_path / "tasks",
        deepseek_api_key="sk-test",
    )
    return TestClient(create_app(settings))


def test_download_legacy_artifact(tmp_path):
    client = _client(tmp_path)
    created = client.post("/api/tasks", json={"model": "deepseek:deepseek-chat"}).json()
    task_id = created["task_id"]

    storage = client.app.state.storage
    storage.write_text(task_id, "artifacts/report.html", "<h1>报告</h1>")

    response = client.get(f"/api/tasks/{task_id}/artifacts/report.html")

    assert response.status_code == 200
    assert response.text == "<h1>报告</h1>"
    assert response.headers["content-type"].startswith("text/html")


def test_download_run_scoped_artifact(tmp_path):
    client = _client(tmp_path)
    created = client.post("/api/tasks", json={"model": "deepseek:deepseek-chat"}).json()
    task_id = created["task_id"]

    storage = client.app.state.storage
    _, run_id = storage.start_run(
        task_id,
        message="生成报告",
        model="deepseek:deepseek-chat",
        expected_statuses={"idle"},
    )
    storage.write_run_text(task_id, run_id, "report.html", "<h1>本轮报告</h1>")
    storage.update_task_if_status(task_id, {"running"}, status="complete", run_id=run_id)

    response = client.get(f"/api/tasks/{task_id}/runs/{run_id}/artifacts/report.html")

    assert response.status_code == 200
    assert response.text == "<h1>本轮报告</h1>"


def test_download_missing_artifact_returns_404(tmp_path):
    client = _client(tmp_path)
    created = client.post("/api/tasks", json={"model": "deepseek:deepseek-chat"}).json()

    response = client.get(f"/api/tasks/{created['task_id']}/artifacts/missing.html")

    assert response.status_code == 404


def test_download_rejects_invalid_artifact_name(tmp_path):
    client = _client(tmp_path)
    created = client.post("/api/tasks", json={"model": "deepseek:deepseek-chat"}).json()

    response = client.get(f"/api/tasks/{created['task_id']}/artifacts/%2e%2e")

    assert response.status_code == 400

