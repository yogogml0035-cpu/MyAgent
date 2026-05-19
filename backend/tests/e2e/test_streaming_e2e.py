from __future__ import annotations

import json
import threading

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.fakes import InMemoryTaskStorage


@pytest.fixture
def app_client(tmp_path):
    settings = Settings(
        task_root=tmp_path / "tasks",
        workspace_root=tmp_path / "tasks",
    )
    app = create_app(settings, storage=InMemoryTaskStorage(settings.task_root))
    return TestClient(app)


def _collect_sse(client, url):
    with client.stream("GET", url) as response:
        events = []
        buffer = ""
        for text in response.iter_text():
            buffer += text
            while "\n\n" in buffer:
                block, buffer = buffer.split("\n\n", 1)
                for line in block.split("\n"):
                    if line.startswith("data: "):
                        events.append(json.loads(line[6:]))
        if buffer.strip():
            for line in buffer.strip().split("\n"):
                if line.startswith("data: "):
                    events.append(json.loads(line[6:]))
        return events


class TestSSEStreamingE2E:
    def test_sse_sends_full_event_records(self, app_client):
        create_resp = app_client.post("/api/tasks", json={"model": "deepseek-v4-flash"})
        task_id = create_resp.json()["task_id"]
        storage = app_client.app.state.storage
        run_id = "run-test-001"

        storage.append_event(
            task_id,
            "tool_call",
            "调用搜索工具",
            {"tool_name": "search", "arguments": {"query": "test"}},
            run_id=run_id,
        )
        storage.append_event(
            task_id,
            "tool_result",
            "搜索完成",
            {"tool_name": "search", "result": "found"},
            run_id=run_id,
        )
        storage.append_event(
            task_id,
            "status_update",
            "状态更新",
            {"status": "processing"},
            run_id=run_id,
        )
        storage.append_event(
            task_id,
            "assistant_answer_delta",
            "回答片段",
            {"content": "这是回答"},
            run_id=run_id,
        )

        storage.update_task_if_status(task_id, {"idle"}, status="complete")

        events = _collect_sse(app_client, f"/api/tasks/{task_id}/stream")

        data_events = [e for e in events if e.get("type") != "done"]
        done_events = [e for e in events if e.get("type") == "done"]

        assert len(done_events) == 1
        assert len(data_events) == 5

        event_types = {e["type"] for e in data_events}
        assert "task_created" in event_types
        assert "tool_call" in event_types
        assert "tool_result" in event_types
        assert "status_update" in event_types
        assert "assistant_answer_delta" in event_types

        for event in data_events:
            assert isinstance(event.get("id"), str)
            assert isinstance(event.get("type"), str)
            assert isinstance(event.get("message"), str)
            assert isinstance(event.get("payload"), dict)
            assert "run_id" in event
            assert "level" in event
            assert isinstance(event.get("created_at"), str)
            assert isinstance(event.get("session_id"), str)
            assert isinstance(event.get("seq"), int)
            if event["type"] in {"tool_call", "tool_result", "status_update", "assistant_answer_delta"}:
                assert event.get("run_id") == run_id

    def test_sse_done_after_runner_stops(self, app_client):
        create_resp = app_client.post("/api/tasks", json={"model": "deepseek-v4-flash"})
        task_id = create_resp.json()["task_id"]
        storage = app_client.app.state.storage

        state, run_id = storage.start_run(
            task_id,
            message="test done signal",
            model="deepseek-v4-flash",
            expected_statuses={"idle"},
        )

        for i in range(3):
            storage.append_event(
                task_id,
                "tool_result",
                f"result {i}",
                {"output": f"data {i}"},
                run_id=run_id,
            )

        storage.update_task_if_status(
            task_id,
            {"running"},
            status="complete",
            run_id=run_id,
        )

        events = _collect_sse(app_client, f"/api/tasks/{task_id}/stream")

        assert len(events) >= 4
        assert events[-1].get("type") == "done"

        data_events = [e for e in events if e.get("type") != "done"]
        assert len(data_events) == 4

        for event in data_events:
            assert "id" in event
            assert "payload" in event

    def test_sse_drains_remaining_events_before_done(self, app_client):
        create_resp = app_client.post("/api/tasks", json={"model": "deepseek-v4-flash"})
        task_id = create_resp.json()["task_id"]
        storage = app_client.app.state.storage
        runner = app_client.app.state.runner

        state, run_id = storage.start_run(
            task_id,
            message="concurrent test",
            model="deepseek-v4-flash",
            expected_statuses={"idle"},
        )

        storage.append_event(task_id, "status_update", "运行开始", {}, run_id=run_id)

        original_is_running = runner.is_running
        events_appended = threading.Event()

        def mock_is_running(tid):
            if tid != task_id:
                return original_is_running(tid)
            return not events_appended.is_set()

        runner.is_running = mock_is_running

        appended_ids = []

        def append_events():
            for i in range(5):
                record = storage.append_event(
                    task_id,
                    "assistant_answer_delta",
                    f"chunk {i}",
                    {"content": f"chunk {i}"},
                    run_id=run_id,
                )
                appended_ids.append(record.id)
            events_appended.set()

        timer = threading.Timer(0.2, append_events)
        timer.start()

        try:
            sse_events = _collect_sse(app_client, f"/api/tasks/{task_id}/stream")
        finally:
            runner.is_running = original_is_running
            timer.join()

        done_events = [e for e in sse_events if e.get("type") == "done"]
        data_events = [e for e in sse_events if e.get("type") != "done"]

        assert len(done_events) == 1

        delta_events = [e for e in data_events if e["type"] == "assistant_answer_delta"]
        assert len(delta_events) == 5

        received_ids = {e["id"] for e in delta_events}
        assert received_ids == set(appended_ids)

        for event in delta_events:
            assert event.get("run_id") == run_id
            assert "content" in event.get("payload", {})
