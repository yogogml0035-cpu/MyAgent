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


class TestCancelTask:
    def test_cancel_idle_task_returns_409(self, create_idle_task, app_client):
        created = create_idle_task()
        response = app_client.post(f"/api/tasks/{created['task_id']}/cancel")
        assert response.status_code == 409

    def test_cancel_nonexistent_task_404(self, app_client):
        response = app_client.post("/api/tasks/nonexistent-id/cancel")
        assert response.status_code == 404
