from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.fakes import InMemoryTaskStorage


def _client(tmp_path):
    settings = Settings(
        task_root=tmp_path / "tasks",
        workspace_root=tmp_path / "tasks",
        deepseek_api_key="sk-test",
    )
    return TestClient(create_app(settings, storage=InMemoryTaskStorage(settings.task_root)))


def test_download_legacy_artifact(tmp_path):
    client = _client(tmp_path)
    created = client.post("/api/tasks", json={"model": "deepseek-v4-flash"}).json()
    task_id = created["task_id"]

    storage = client.app.state.storage
    storage.write_text(task_id, "artifacts/report.html", "<h1>报告</h1>")

    response = client.get(f"/api/tasks/{task_id}/artifacts/report.html")

    assert response.status_code == 200
    assert response.text == "<h1>报告</h1>"
    assert response.headers["content-type"].startswith("text/html")


def test_download_run_scoped_artifact(tmp_path):
    client = _client(tmp_path)
    created = client.post("/api/tasks", json={"model": "deepseek-v4-flash"}).json()
    task_id = created["task_id"]

    storage = client.app.state.storage
    _, run_id = storage.start_run(
        task_id,
        message="生成报告",
        model="deepseek-v4-flash",
        expected_statuses={"idle"},
    )
    storage.write_run_text(task_id, run_id, "report.html", "<h1>本轮报告</h1>")
    storage.update_task_if_status(task_id, {"running"}, status="complete", run_id=run_id)

    response = client.get(f"/api/tasks/{task_id}/runs/{run_id}/artifacts/report.html")

    assert response.status_code == 200
    assert response.text == "<h1>本轮报告</h1>"


def test_download_fixed_run_artifact_through_legacy_url_before_completion(tmp_path):
    client = _client(tmp_path)
    created = client.post("/api/tasks", json={"model": "deepseek-v4-flash"}).json()
    task_id = created["task_id"]

    storage = client.app.state.storage
    _, run_id = storage.start_run(
        task_id,
        message="生成报告",
        model="deepseek-v4-flash",
        expected_statuses={"idle"},
    )
    storage.write_run_text(task_id, run_id, "report.html", "<h1>镜像报告</h1>")

    response = client.get(f"/api/tasks/{task_id}/artifacts/report.html")

    assert response.status_code == 200
    assert response.text == "<h1>镜像报告</h1>"


def test_download_latest_completed_run_artifact_through_compat_url(tmp_path):
    client = _client(tmp_path)
    created = client.post("/api/tasks", json={"model": "deepseek-v4-flash"}).json()
    task_id = created["task_id"]

    storage = client.app.state.storage
    _, first_run_id = storage.start_run(
        task_id,
        message="第一次生成",
        model="deepseek-v4-flash",
        expected_statuses={"idle"},
    )
    storage.write_run_text(task_id, first_run_id, "analysis-extra.json", '{"version": 1}')
    storage.update_task_if_status(task_id, {"running"}, status="complete", run_id=first_run_id)
    _, second_run_id = storage.start_run(
        task_id,
        message="第二次生成",
        model="deepseek-v4-flash",
        expected_statuses={"complete"},
    )
    storage.write_run_text(task_id, second_run_id, "analysis-extra.json", '{"version": 2}')
    storage.update_task_if_status(task_id, {"running"}, status="complete", run_id=second_run_id)

    latest_response = client.get(f"/api/tasks/{task_id}/artifacts/analysis-extra.json")
    first_run_response = client.get(
        f"/api/tasks/{task_id}/runs/{first_run_id}/artifacts/analysis-extra.json"
    )
    task_response = client.get(f"/api/tasks/{task_id}")

    assert latest_response.status_code == 200
    assert latest_response.text == '{"version": 2}'
    assert first_run_response.status_code == 200
    assert first_run_response.text == '{"version": 1}'
    artifacts = task_response.json()["artifacts"]
    artifact_urls = {artifact["run_id"]: artifact["url"] for artifact in artifacts}
    assert artifact_urls == {
        first_run_id: f"/api/tasks/{task_id}/runs/{first_run_id}/artifacts/analysis-extra.json",
        second_run_id: f"/api/tasks/{task_id}/runs/{second_run_id}/artifacts/analysis-extra.json",
    }


def test_run_scoped_download_requires_recorded_artifact(tmp_path):
    client = _client(tmp_path)
    created = client.post("/api/tasks", json={"model": "deepseek-v4-flash"}).json()
    task_id = created["task_id"]

    storage = client.app.state.storage
    _, run_id = storage.start_run(
        task_id,
        message="生成隐藏文件",
        model="deepseek-v4-flash",
        expected_statuses={"idle"},
    )
    raw_path = storage.run_artifact_dir(task_id, run_id) / "unrecorded.txt"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text("should stay hidden", encoding="utf-8")

    response = client.get(f"/api/tasks/{task_id}/runs/{run_id}/artifacts/unrecorded.txt")

    assert response.status_code == 404


def test_download_missing_artifact_returns_404(tmp_path):
    client = _client(tmp_path)
    created = client.post("/api/tasks", json={"model": "deepseek-v4-flash"}).json()

    response = client.get(f"/api/tasks/{created['task_id']}/artifacts/missing.html")

    assert response.status_code == 404


def test_download_rejects_invalid_artifact_name(tmp_path):
    client = _client(tmp_path)
    created = client.post("/api/tasks", json={"model": "deepseek-v4-flash"}).json()

    response = client.get(f"/api/tasks/{created['task_id']}/artifacts/%2e%2e")

    assert response.status_code == 400
