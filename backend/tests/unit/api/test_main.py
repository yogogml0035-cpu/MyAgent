from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import RequestBodyTooLarge, create_app, install_receive_body_limit
from tests.fakes import InMemoryTaskStorage

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
    app = create_app(settings, storage=InMemoryTaskStorage(settings.task_root))
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


def test_lifespan_requires_external_storage_and_memory_services(tmp_path):
    settings = Settings(
        task_root=tmp_path / "tasks",
        workspace_root=tmp_path / "tasks",
    )
    app = create_app(settings)

    try:
        with TestClient(app):
            pass
    except RuntimeError as exc:
        assert "MYAGENT_DATABASE_URL" in str(exc)
        assert "DASHSCOPE_API_KEY" in str(exc)
    else:
        raise AssertionError("Expected startup to fail without required services")


def test_multipart_content_length_limit_rejects_before_storage(tmp_path, monkeypatch):
    settings = Settings(
        task_root=tmp_path / "tasks",
        workspace_root=tmp_path / "tasks",
        deepseek_api_key="sk-test",
        max_upload_request_bytes=8,
    )
    storage = InMemoryTaskStorage(settings.task_root)
    app = create_app(settings, storage=storage)
    client = TestClient(app)
    task_id = client.post("/api/tasks", json={"model": "deepseek:deepseek-chat"}).json()["task_id"]
    called = False

    def fail_if_called(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("storage.save_uploads should not run for oversized multipart")

    monkeypatch.setattr(storage, "save_uploads", fail_if_called)

    response = client.post(
        f"/api/tasks/{task_id}/files",
        files={"files": ("big.md", b"large payload", "text/markdown")},
    )

    assert response.status_code == 413
    assert called is False


def test_receive_body_limit_rejects_chunked_body_before_parser():
    async def run() -> None:
        messages = [
            {"type": "http.request", "body": b"1234", "more_body": True},
            {"type": "http.request", "body": b"5678", "more_body": True},
            {"type": "http.request", "body": b"9", "more_body": False},
        ]

        async def receive():
            return messages.pop(0)

        class FakeRequest:
            _receive = staticmethod(receive)

        request: Any = FakeRequest()
        install_receive_body_limit(request, 8, "上传请求")

        assert await request._receive() == {
            "type": "http.request",
            "body": b"1234",
            "more_body": True,
        }
        assert await request._receive() == {
            "type": "http.request",
            "body": b"5678",
            "more_body": True,
        }
        try:
            await request._receive()
        except RequestBodyTooLarge as exc:
            assert "上传请求超过 8 字节限制" in str(exc)
        else:
            raise AssertionError("expected RequestBodyTooLarge")

    asyncio.run(run())
