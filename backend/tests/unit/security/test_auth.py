from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def _make_app_with_token(tmp_path, access_token: str = "test-secret"):
    settings = Settings(
        task_root=tmp_path / "tasks",
        workspace_root=tmp_path / "tasks",
        access_token=access_token,
    )
    app = create_app(settings)
    return TestClient(app)


class TestAccessTokenAuth:
    """Test that MYAGENT_ACCESS_TOKEN gates all /api/ endpoints."""

    def test_no_token_returns_401(self, tmp_path):
        client = _make_app_with_token(tmp_path)
        resp = client.get("/api/tasks")
        assert resp.status_code == 401

    def test_header_x_myagent_token_passes(self, tmp_path):
        client = _make_app_with_token(tmp_path)
        resp = client.get("/api/tasks", headers={"X-MyAgent-Token": "test-secret"})
        assert resp.status_code == 200

    def test_bearer_token_passes(self, tmp_path):
        client = _make_app_with_token(tmp_path)
        resp = client.get(
            "/api/tasks", headers={"Authorization": "Bearer test-secret"}
        )
        assert resp.status_code == 200

    def test_wrong_token_returns_401(self, tmp_path):
        client = _make_app_with_token(tmp_path)
        resp = client.get("/api/tasks", headers={"X-MyAgent-Token": "wrong"})
        assert resp.status_code == 401

    def test_query_param_token_passes(self, tmp_path):
        client = _make_app_with_token(tmp_path)
        resp = client.get("/api/tasks?token=test-secret")
        assert resp.status_code == 200

    def test_wrong_query_param_token_returns_401(self, tmp_path):
        client = _make_app_with_token(tmp_path)
        resp = client.get("/api/tasks?token=wrong")
        assert resp.status_code == 401

    def test_query_param_token_on_sse_stream(self, tmp_path):
        """SSE streaming endpoint should accept token via query param."""
        client = _make_app_with_token(tmp_path)
        create_resp = client.post(
            "/api/tasks?token=test-secret",
            json={"model": "deepseek:deepseek-chat"},
        )
        assert create_resp.status_code == 201
        task_id = create_resp.json()["task_id"]
        resp = client.get(f"/api/tasks/{task_id}/stream?token=test-secret")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "text/event-stream; charset=utf-8"

    def test_sse_stream_without_token_returns_401(self, tmp_path):
        """SSE streaming without token should be rejected."""
        client = _make_app_with_token(tmp_path)
        create_resp = client.post(
            "/api/tasks?token=test-secret",
            json={"model": "deepseek:deepseek-chat"},
        )
        task_id = create_resp.json()["task_id"]
        resp = client.get(f"/api/tasks/{task_id}/stream")
        assert resp.status_code == 401

    def test_legacy_header_x_agent_chat_token_passes(self, tmp_path):
        client = _make_app_with_token(tmp_path)
        resp = client.get(
            "/api/tasks", headers={"X-Agent-Chat-Token": "test-secret"}
        )
        assert resp.status_code == 200


class TestLocalOnlyAccess:
    """Test that without access_token, loopback clients are allowed."""

    def test_loopback_client_allowed_without_token(self, tmp_path):
        settings = Settings(
            task_root=tmp_path / "tasks",
            workspace_root=tmp_path / "tasks",
        )
        app = create_app(settings)
        client = TestClient(app)
        resp = client.get("/api/tasks")
        assert resp.status_code == 200
