from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def app_client(tmp_path):
    settings = Settings(
        task_root=tmp_path / "tasks",
        workspace_root=tmp_path / "tasks",
        deepseek_api_key="sk-test",
    )
    app = create_app(settings)
    return TestClient(app)


@pytest.fixture
def create_idle_task(app_client):
    def _create(model="deepseek:deepseek-chat"):
        response = app_client.post(
            "/api/tasks",
            json={"model": model},
        )
        assert response.status_code == 201
        return response.json()

    return _create


class TestCreateTask:
    def test_create_task_returns_201(self, app_client):
        response = app_client.post("/api/tasks", json={"model": "deepseek:deepseek-chat"})
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "idle"
        assert data["task_id"]
        assert data["model"] == "deepseek:deepseek-chat"

    def test_create_task_without_message_is_idle(self, app_client):
        response = app_client.post("/api/tasks", json={"model": "deepseek:deepseek-chat"})
        data = response.json()
        assert data["status"] == "idle"
        assert data["messages"] == []

    def test_create_task_rejects_unknown_model(self, app_client):
        response = app_client.post("/api/tasks", json={"model": "fake:model"})

        assert response.status_code == 400
        assert response.json()["detail"] == "模型不在允许列表中"

    def test_create_task_with_message_requires_configured_provider_key(self, tmp_path):
        settings = Settings(
            task_root=tmp_path / "tasks",
            workspace_root=tmp_path / "tasks",
        )
        client = TestClient(create_app(settings))

        response = client.post(
            "/api/tasks",
            json={"message": "hello", "model": "deepseek:deepseek-chat"},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "模型服务未配置，请先在后端配置对应 API Key"


class TestGetTask:
    def test_get_idle_task_returns_state(self, create_idle_task, app_client):
        created = create_idle_task()
        response = app_client.get(f"/api/tasks/{created['task_id']}")
        assert response.status_code == 200
        assert response.json()["task_id"] == created["task_id"]

    def test_get_nonexistent_task_returns_404(self, app_client):
        response = app_client.get("/api/tasks/nonexistent-id")
        assert response.status_code == 404

    def test_newly_created_task_is_accessible(self, app_client):
        create_resp = app_client.post("/api/tasks", json={"model": "deepseek:deepseek-chat"})
        task_id = create_resp.json()["task_id"]
        get_resp = app_client.get(f"/api/tasks/{task_id}")
        assert get_resp.status_code == 200
        state = get_resp.json()
        assert state["status"] == "idle"
        assert state["messages"] == []

    def test_get_task_can_omit_events_for_lightweight_refresh(self, create_idle_task, app_client):
        created = create_idle_task()
        response = app_client.get(f"/api/tasks/{created['task_id']}?include_events=false")

        assert response.status_code == 200
        assert response.json()["events"] == []


class TestGetEvents:
    def test_get_events_for_idle_task(self, create_idle_task, app_client):
        created = create_idle_task()
        response = app_client.get(f"/api/tasks/{created['task_id']}/events")
        assert response.status_code == 200
        events = response.json()
        assert isinstance(events, list)
        assert any(e["type"] == "task_created" for e in events)

    def test_get_events_nonexistent_task_404(self, app_client):
        response = app_client.get("/api/tasks/nonexistent-id/events")
        assert response.status_code == 404


class TestSendMessage:
    def test_send_message_to_idle_task_succeeds(self, create_idle_task, app_client):
        created = create_idle_task()
        runner = app_client.app.state.runner
        original_start = runner.start_background

        def mock_start_background(*args, **kwargs):
            pass

        runner.start_background = mock_start_background
        try:
            response = app_client.post(
                f"/api/tasks/{created['task_id']}/messages",
                json={"message": "hello", "model": "deepseek:deepseek-chat"},
            )
        finally:
            runner.start_background = original_start

        assert response.status_code == 200
        state = response.json()
        assert state["status"] == "running"
        assert any(m["role"] == "user" for m in state["messages"])

    def test_send_message_to_nonexistent_task_404(self, app_client):
        response = app_client.post(
            "/api/tasks/nonexistent-id/messages",
            json={"message": "hello", "model": "deepseek:deepseek-chat"},
        )
        assert response.status_code == 404

    def test_send_message_adds_user_message(self, create_idle_task, app_client):
        created = create_idle_task()
        runner = app_client.app.state.runner
        original_start = runner.start_background

        def mock_start_background(*args, **kwargs):
            pass

        runner.start_background = mock_start_background
        try:
            response = app_client.post(
                f"/api/tasks/{created['task_id']}/messages",
                json={"message": "test message content", "model": "deepseek:deepseek-chat"},
            )
        finally:
            runner.start_background = original_start

        assert response.status_code == 200
        messages = response.json()["messages"]
        user_messages = [m for m in messages if m["role"] == "user"]
        assert len(user_messages) == 1
        assert user_messages[0]["content"] == "test message content"

    def test_send_message_requires_configured_provider_key(self, tmp_path):
        settings = Settings(
            task_root=tmp_path / "tasks",
            workspace_root=tmp_path / "tasks",
        )
        client = TestClient(create_app(settings))
        created = client.post("/api/tasks", json={"model": "deepseek:deepseek-chat"}).json()

        response = client.post(
            f"/api/tasks/{created['task_id']}/messages",
            json={"message": "hello", "model": "deepseek:deepseek-chat"},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "模型服务未配置，请先在后端配置对应 API Key"


class TestUploadFiles:
    def test_upload_to_idle_task_succeeds(self, create_idle_task, app_client):
        created = create_idle_task()
        response = app_client.post(
            f"/api/tasks/{created['task_id']}/files",
            files={"files": ("test.md", b"# test content", "text/markdown")},
        )
        assert response.status_code == 201

    def test_upload_to_nonexistent_task_404(self, app_client):
        response = app_client.post(
            "/api/tasks/nonexistent-id/files",
            files={"files": ("test.md", b"# test", "text/markdown")},
        )
        assert response.status_code == 404

    def test_upload_duplicate_file_returns_409(self, create_idle_task, app_client):
        created = create_idle_task()
        task_id = created["task_id"]
        first = app_client.post(
            f"/api/tasks/{task_id}/files",
            files={"files": ("test.md", b"# test", "text/markdown")},
        )
        assert first.status_code == 201

        response = app_client.post(
            f"/api/tasks/{task_id}/files",
            files={"files": ("test.md", b"# again", "text/markdown")},
        )

        assert response.status_code == 409
        assert "上传文件已存在" in response.json()["detail"]

    def test_upload_unsupported_extension_returns_400(self, create_idle_task, app_client):
        created = create_idle_task()

        response = app_client.post(
            f"/api/tasks/{created['task_id']}/files",
            files={"files": ("notes.txt", b"hello", "text/plain")},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "仅支持上传 Markdown 或 JSON 文件"

    def test_upload_invalid_json_returns_400_without_partial_file(self, create_idle_task, app_client):
        created = create_idle_task()
        task_id = created["task_id"]

        response = app_client.post(
            f"/api/tasks/{task_id}/files",
            files={"files": ("data.json", b"{invalid", "application/json")},
        )

        assert response.status_code == 400
        assert "内容不是合法 JSON" in response.json()["detail"]
        assert app_client.app.state.storage.list_uploads(task_id) == []

    def test_upload_over_file_count_limit_returns_413(self, tmp_path):
        settings = Settings(
            task_root=tmp_path / "tasks",
            workspace_root=tmp_path / "tasks",
            deepseek_api_key="sk-test",
            max_upload_files=1,
        )
        client = TestClient(create_app(settings))
        created = client.post("/api/tasks", json={"model": "deepseek:deepseek-chat"}).json()

        response = client.post(
            f"/api/tasks/{created['task_id']}/files",
            files=[
                ("files", ("a.md", b"a", "text/markdown")),
                ("files", ("b.md", b"b", "text/markdown")),
            ],
        )

        assert response.status_code == 413

    def test_upload_over_file_size_limit_returns_413(self, tmp_path):
        settings = Settings(
            task_root=tmp_path / "tasks",
            workspace_root=tmp_path / "tasks",
            deepseek_api_key="sk-test",
            max_upload_file_bytes=4,
        )
        client = TestClient(create_app(settings))
        created = client.post("/api/tasks", json={"model": "deepseek:deepseek-chat"}).json()

        response = client.post(
            f"/api/tasks/{created['task_id']}/files",
            files={"files": ("big.md", b"12345", "text/markdown")},
        )

        assert response.status_code == 413


class TestCancelTask:
    def test_cancel_idle_task_returns_409(self, create_idle_task, app_client):
        created = create_idle_task()
        response = app_client.post(f"/api/tasks/{created['task_id']}/cancel")
        assert response.status_code == 409

    def test_cancel_nonexistent_task_404(self, app_client):
        response = app_client.post("/api/tasks/nonexistent-id/cancel")
        assert response.status_code == 404
