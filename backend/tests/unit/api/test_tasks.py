from __future__ import annotations

from typing import Any, cast

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
        deepseek_api_key="sk-test",
    )

    async def title_generator(message: str, model: str, settings: Settings) -> str:
        return "模型会话名"

    app = create_app(
        settings,
        storage=InMemoryTaskStorage(settings.task_root),
        title_generator=title_generator,
    )
    return TestClient(app)


@pytest.fixture
def create_idle_task(app_client):
    def _create(model="deepseek-v4-flash"):
        response = app_client.post(
            "/api/tasks",
            json={"model": model},
        )
        assert response.status_code == 201
        return response.json()

    return _create


class TestCreateTask:
    def test_create_task_returns_201(self, app_client):
        response = app_client.post("/api/tasks", json={"model": "deepseek-v4-flash"})
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "idle"
        assert data["task_id"]
        assert data["model"] == "deepseek-v4-flash"

    def test_create_task_without_message_is_idle(self, app_client):
        response = app_client.post("/api/tasks", json={"model": "deepseek-v4-flash"})
        data = response.json()
        assert data["status"] == "idle"
        assert data["messages"] == []

    def test_create_task_without_model_uses_configured_default_model(self, tmp_path):
        settings = Settings(
            task_root=tmp_path / "tasks",
            workspace_root=tmp_path / "tasks",
            default_model="deepseek-v4-flash-thinking",
            deepseek_api_key="sk-test",
        )
        client = TestClient(create_app(settings, storage=InMemoryTaskStorage(settings.task_root)))

        response = client.post("/api/tasks", json={})

        assert response.status_code == 201
        assert response.json()["model"] == "deepseek-v4-flash-thinking"

    def test_create_task_with_message_without_model_requires_default_provider_key(self, tmp_path):
        settings = Settings(
            task_root=tmp_path / "tasks",
            workspace_root=tmp_path / "tasks",
            default_model="deepseek-v4-flash-thinking",
        )
        client = TestClient(create_app(settings, storage=InMemoryTaskStorage(settings.task_root)))

        response = client.post("/api/tasks", json={"message": "hello"})

        assert response.status_code == 400
        assert response.json()["detail"] == "模型服务未配置，请先在后端配置对应 API Key"

    def test_create_task_rejects_unknown_model(self, app_client):
        response = app_client.post("/api/tasks", json={"model": "fake:model"})

        assert response.status_code == 400
        assert response.json()["detail"] == "模型不在允许列表中"

    def test_create_task_with_message_requires_configured_provider_key(self, tmp_path):
        settings = Settings(
            task_root=tmp_path / "tasks",
            workspace_root=tmp_path / "tasks",
        )
        client = TestClient(create_app(settings, storage=InMemoryTaskStorage(settings.task_root)))

        response = client.post(
            "/api/tasks",
            json={"message": "hello", "model": "deepseek-v4-flash"},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "模型服务未配置，请先在后端配置对应 API Key"

    def test_create_task_with_message_sets_model_generated_history_title(self, tmp_path):
        settings = Settings(
            task_root=tmp_path / "tasks",
            workspace_root=tmp_path / "tasks",
            deepseek_api_key="sk-test",
        )
        generated: dict[str, str] = {}

        async def title_generator(message: str, model: str, settings: Settings) -> str:
            generated["message"] = message
            generated["model"] = model
            return "需求命名"

        client = TestClient(
            create_app(
                settings,
                storage=InMemoryTaskStorage(settings.task_root),
                title_generator=title_generator,
            )
        )
        runner = cast(Any, client.app).state.runner
        original_start = runner.start_background
        runner.start_background = lambda *args, **kwargs: None
        try:
            response = client.post(
                "/api/tasks",
                json={"message": "请帮我总结用户消息并命名", "model": "deepseek-v4-flash"},
            )
        finally:
            runner.start_background = original_start

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "需求命名"
        summaries = client.get("/api/tasks").json()
        assert summaries[0]["title"] == "需求命名"
        assert generated == {
            "message": "请帮我总结用户消息并命名",
            "model": "deepseek-v4-flash",
        }

    def test_create_task_with_message_starts_runner_when_auto_title_fails(self, tmp_path):
        settings = Settings(
            task_root=tmp_path / "tasks",
            workspace_root=tmp_path / "tasks",
            deepseek_api_key="sk-test",
        )

        async def title_generator(message: str, model: str, settings: Settings) -> str:
            raise RuntimeError("title provider failed")

        client = TestClient(
            create_app(
                settings,
                storage=InMemoryTaskStorage(settings.task_root),
                title_generator=title_generator,
            )
        )
        runner = cast(Any, client.app).state.runner
        original_start = runner.start_background
        started: dict[str, str] = {}

        def mock_start_background(task_id: str, message: str, *, model: str, run_id: str) -> None:
            started.update(
                {
                    "task_id": task_id,
                    "message": message,
                    "model": model,
                    "run_id": run_id,
                }
            )

        runner.start_background = mock_start_background
        try:
            response = client.post(
                "/api/tasks",
                json={
                    "message": "标题生成失败也必须启动任务",
                    "model": "deepseek-v4-flash",
                },
            )
        finally:
            runner.start_background = original_start

        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "running"
        assert data["title"] is None
        assert started == {
            "task_id": data["task_id"],
            "message": "标题生成失败也必须启动任务",
            "model": "deepseek-v4-flash",
            "run_id": data["active_run_id"],
        }


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
        create_resp = app_client.post("/api/tasks", json={"model": "deepseek-v4-flash"})
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


class TestTaskHistoryActions:
    def test_rename_task_updates_history_title(self, create_idle_task, app_client):
        created = create_idle_task()
        task_id = created["task_id"]
        runner = app_client.app.state.runner
        original_start = runner.start_background

        def mock_start_background(*args, **kwargs):
            pass

        runner.start_background = mock_start_background
        try:
            message_response = app_client.post(
                f"/api/tasks/{task_id}/messages",
                json={"message": "原始标题内容", "model": "deepseek-v4-flash"},
            )
        finally:
            runner.start_background = original_start
        assert message_response.status_code == 200

        response = app_client.patch(
            f"/api/tasks/{task_id}",
            json={"title": "  项目复盘  "},
        )

        assert response.status_code == 200
        assert response.json()["title"] == "项目复盘"
        summaries = app_client.get("/api/tasks").json()
        assert any(item["task_id"] == task_id and item["title"] == "项目复盘" for item in summaries)

    def test_rename_task_rejects_blank_title(self, create_idle_task, app_client):
        created = create_idle_task()

        response = app_client.patch(
            f"/api/tasks/{created['task_id']}",
            json={"title": "   "},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "会话名称不能为空"

    def test_delete_task_removes_task_state(self, create_idle_task, app_client):
        created = create_idle_task()
        task_id = created["task_id"]
        task_dir = app_client.app.state.storage.task_dir(task_id)
        assert task_dir.is_dir()

        response = app_client.delete(f"/api/tasks/{task_id}")

        assert response.status_code == 204
        assert app_client.get(f"/api/tasks/{task_id}").status_code == 404
        assert not task_dir.exists()

    def test_delete_running_task_returns_409(self, create_idle_task, app_client):
        created = create_idle_task()
        task_id = created["task_id"]
        storage = app_client.app.state.storage
        assert storage.start_run(
            task_id,
            message="hello",
            model="deepseek-v4-flash",
            expected_statuses={"idle"},
        )

        response = app_client.delete(f"/api/tasks/{task_id}")

        assert response.status_code == 409
        assert response.json()["detail"] == "任务运行中，不能删除"


class TestGetEvents:
    def test_get_events_for_idle_task(self, create_idle_task, app_client):
        created = create_idle_task()
        response = app_client.get(f"/api/tasks/{created['task_id']}/events")
        assert response.status_code == 200
        events = response.json()
        assert isinstance(events, list)
        assert any(e["type"] == "task_created" for e in events)

    def test_get_events_after_known_id_returns_later_events(self, create_idle_task, app_client):
        created = create_idle_task()
        task_id = created["task_id"]
        storage = app_client.app.state.storage
        first = storage.append_event(task_id, "first_event", "first")
        second = storage.append_event(task_id, "second_event", "second")

        response = app_client.get(f"/api/tasks/{task_id}/events?after_id={first.id}")

        assert response.status_code == 200
        assert [event["id"] for event in response.json()] == [second.id]

    def test_get_events_after_unknown_id_recovers_with_full_event_stream(
        self, create_idle_task, app_client
    ):
        created = create_idle_task()
        task_id = created["task_id"]
        app_client.app.state.storage.append_event(task_id, "test_event", "something happened")

        response = app_client.get(f"/api/tasks/{task_id}/events?after_id=missing-event-id")

        assert response.status_code == 200
        events = response.json()
        assert [event["seq"] for event in events] == [1, 2]

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
                json={"message": "hello", "model": "deepseek-v4-flash"},
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
            json={"message": "hello", "model": "deepseek-v4-flash"},
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
                json={"message": "test message content", "model": "deepseek-v4-flash"},
            )
        finally:
            runner.start_background = original_start

        assert response.status_code == 200
        messages = response.json()["messages"]
        user_messages = [m for m in messages if m["role"] == "user"]
        assert len(user_messages) == 1
        assert user_messages[0]["content"] == "test message content"

    def test_send_message_to_running_task_returns_409_without_creating_second_run(
        self, create_idle_task, app_client
    ):
        created = create_idle_task()
        task_id = created["task_id"]
        storage = app_client.app.state.storage
        run_result = storage.start_run(
            task_id,
            message="first message",
            model="deepseek-v4-flash",
            expected_statuses={"idle"},
        )
        assert run_result is not None
        _, run_id = run_result

        runner = app_client.app.state.runner
        original_is_running = runner.is_running
        runner.is_running = lambda candidate_task_id: candidate_task_id == task_id
        try:
            response = app_client.post(
                f"/api/tasks/{task_id}/messages",
                json={"message": "second message", "model": "deepseek-v4-flash"},
            )
        finally:
            runner.is_running = original_is_running

        assert response.status_code == 409
        assert response.json()["detail"] == "任务运行中，请等待完成后再发送消息"
        state = app_client.get(f"/api/tasks/{task_id}").json()
        assert state["status"] == "running"
        assert state["active_run_id"] == run_id
        assert [run["id"] for run in state["runs"]] == [run_id]
        assert [message["content"] for message in state["messages"]] == ["first message"]

    def test_send_message_with_skills_formats_storage_title_and_runner(
        self, create_idle_task, app_client
    ):
        created = create_idle_task()
        task_id = created["task_id"]
        runner = app_client.app.state.runner
        original_start = runner.start_background
        captured: dict[str, str] = {}

        async def title_generator(message: str, model: str, settings: Settings) -> str:
            captured["title_message"] = message
            captured["title_model"] = model
            return "skill 会话名"

        def mock_start_background(task_id: str, message: str, *, model: str, run_id: str) -> None:
            captured.update(
                {
                    "runner_task_id": task_id,
                    "runner_message": message,
                    "runner_model": model,
                    "runner_run_id": run_id,
                }
            )

        app_client.app.state.title_generator = title_generator
        runner.start_background = mock_start_background
        try:
            response = app_client.post(
                f"/api/tasks/{task_id}/messages",
                json={
                    "message": "hello",
                    "model": "deepseek-v4-flash",
                    "skills": ["web-research"],
                },
            )
        finally:
            runner.start_background = original_start

        assert response.status_code == 200
        data = response.json()
        effective_message = "[$web-research]\n\nhello"
        assert data["messages"][-1]["content"] == effective_message
        assert data["runs"][-1]["message"] == effective_message
        assert captured == {
            "title_message": effective_message,
            "title_model": "deepseek-v4-flash",
            "runner_task_id": task_id,
            "runner_message": effective_message,
            "runner_model": "deepseek-v4-flash",
            "runner_run_id": data["active_run_id"],
        }

    def test_send_message_with_multiple_skills_preserves_selection_order(
        self, create_idle_task, app_client
    ):
        created = create_idle_task()
        runner = app_client.app.state.runner
        original_start = runner.start_background
        runner.start_background = lambda *args, **kwargs: None
        try:
            response = app_client.post(
                f"/api/tasks/{created['task_id']}/messages",
                json={
                    "message": "review latest findings",
                    "model": "deepseek-v4-flash",
                    "skills": ["code-review", "web-research"],
                },
            )
        finally:
            runner.start_background = original_start

        assert response.status_code == 200
        assert (
            response.json()["messages"][-1]["content"]
            == "[$code-review] [$web-research]\n\nreview latest findings"
        )

    def test_send_message_rejects_unknown_skill_before_starting_run(
        self, create_idle_task, app_client
    ):
        created = create_idle_task()
        task_id = created["task_id"]

        response = app_client.post(
            f"/api/tasks/{task_id}/messages",
            json={
                "message": "hello",
                "model": "deepseek-v4-flash",
                "skills": ["unknown-skill"],
            },
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "未知 skill：unknown-skill"
        state = app_client.get(f"/api/tasks/{task_id}").json()
        assert state["status"] == "idle"
        assert state["messages"] == []
        assert state["runs"] == []

    def test_send_message_limits_skill_count(self, create_idle_task, app_client):
        created = create_idle_task()

        response = app_client.post(
            f"/api/tasks/{created['task_id']}/messages",
            json={
                "message": "hello",
                "model": "deepseek-v4-flash",
                "skills": ["web-research"] * 9,
            },
        )

        assert response.status_code == 422
        assert response.json()["detail"] == "请求参数校验失败，请检查输入内容。"

    def test_send_message_with_skill_and_default_file_prompt(
        self, create_idle_task, app_client
    ):
        created = create_idle_task()
        task_id = created["task_id"]
        upload_response = app_client.post(
            f"/api/tasks/{task_id}/files",
            files={"files": ("test.md", b"# test content", "text/markdown")},
        )
        assert upload_response.status_code == 201
        runner = app_client.app.state.runner
        original_start = runner.start_background
        runner.start_background = lambda *args, **kwargs: None
        try:
            response = app_client.post(
                f"/api/tasks/{task_id}/messages",
                json={
                    "message": "请分析已上传文件，先按需读取资源内容，再总结关键差异。",
                    "model": "deepseek-v4-flash",
                    "skills": ["web-research"],
                },
            )
        finally:
            runner.start_background = original_start

        assert response.status_code == 200
        assert response.json()["messages"][-1]["content"].startswith(
            "[$web-research]\n\n请分析已上传文件"
        )

    def test_send_message_sets_model_generated_history_title(self, create_idle_task, app_client):
        created = create_idle_task()
        runner = app_client.app.state.runner
        original_start = runner.start_background
        runner.start_background = lambda *args, **kwargs: None
        try:
            response = app_client.post(
                f"/api/tasks/{created['task_id']}/messages",
                json={"message": "请总结左侧历史会话标题", "model": "deepseek-v4-flash"},
            )
        finally:
            runner.start_background = original_start

        assert response.status_code == 200
        assert response.json()["title"] == "模型会话名"
        summaries = app_client.get("/api/tasks").json()
        assert summaries[0]["title"] == "模型会话名"

    def test_send_message_starts_runner_when_auto_title_write_fails(
        self, create_idle_task, app_client
    ):
        created = create_idle_task()
        task_id = created["task_id"]
        storage = app_client.app.state.storage
        runner = app_client.app.state.runner
        original_set_title = storage.set_task_title_if_empty
        original_start = runner.start_background
        started: dict[str, str] = {}

        def fail_set_task_title_if_empty(task_id: str, title: str):
            raise RuntimeError("title storage failed")

        def mock_start_background(task_id: str, message: str, *, model: str, run_id: str) -> None:
            started.update(
                {
                    "task_id": task_id,
                    "message": message,
                    "model": model,
                    "run_id": run_id,
                }
            )

        storage.set_task_title_if_empty = fail_set_task_title_if_empty
        runner.start_background = mock_start_background
        try:
            response = app_client.post(
                f"/api/tasks/{task_id}/messages",
                json={"message": "标题写入失败也必须启动任务", "model": "deepseek-v4-flash"},
            )
        finally:
            storage.set_task_title_if_empty = original_set_title
            runner.start_background = original_start

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"
        assert data["title"] is None
        assert started == {
            "task_id": task_id,
            "message": "标题写入失败也必须启动任务",
            "model": "deepseek-v4-flash",
            "run_id": data["active_run_id"],
        }

    def test_send_message_keeps_manual_history_title(self, create_idle_task, app_client):
        created = create_idle_task()
        task_id = created["task_id"]
        runner = app_client.app.state.runner
        original_start = runner.start_background
        runner.start_background = lambda *args, **kwargs: None
        try:
            rename_response = app_client.patch(
                f"/api/tasks/{task_id}",
                json={"title": "手动标题"},
            )
            message_response = app_client.post(
                f"/api/tasks/{task_id}/messages",
                json={"message": "这条消息不应覆盖标题", "model": "deepseek-v4-flash"},
            )
        finally:
            runner.start_background = original_start

        assert rename_response.status_code == 200
        assert message_response.status_code == 200
        assert message_response.json()["title"] == "手动标题"

    def test_send_message_requires_configured_provider_key(self, tmp_path):
        settings = Settings(
            task_root=tmp_path / "tasks",
            workspace_root=tmp_path / "tasks",
        )
        client = TestClient(create_app(settings, storage=InMemoryTaskStorage(settings.task_root)))
        created = client.post("/api/tasks", json={"model": "deepseek-v4-flash"}).json()

        response = client.post(
            f"/api/tasks/{created['task_id']}/messages",
            json={"message": "hello", "model": "deepseek-v4-flash"},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "模型服务未配置，请先在后端配置对应 API Key"

    def test_send_message_without_model_uses_configured_default_model(self, tmp_path):
        settings = Settings(
            task_root=tmp_path / "tasks",
            workspace_root=tmp_path / "tasks",
            default_model="deepseek-v4-flash-thinking",
            deepseek_api_key="sk-test",
        )
        client = TestClient(create_app(settings, storage=InMemoryTaskStorage(settings.task_root)))
        created = client.post("/api/tasks", json={}).json()
        runner = cast(Any, client.app).state.runner
        original_start = runner.start_background
        started: dict[str, str] = {}

        def mock_start_background(*args, **kwargs):
            started["model"] = kwargs["model"]

        runner.start_background = mock_start_background
        try:
            response = client.post(
                f"/api/tasks/{created['task_id']}/messages",
                json={"message": "hello"},
            )
        finally:
            runner.start_background = original_start

        assert response.status_code == 200
        assert response.json()["runs"][0]["model"] == "deepseek-v4-flash-thinking"
        assert started["model"] == "deepseek-v4-flash-thinking"


class TestUploadFiles:
    def test_upload_to_idle_task_succeeds(self, create_idle_task, app_client):
        created = create_idle_task()
        response = app_client.post(
            f"/api/tasks/{created['task_id']}/files",
            files={"files": ("test.md", b"# test content", "text/markdown")},
        )
        assert response.status_code == 201

    def test_upload_accepts_modern_document_resource_formats(self, create_idle_task, app_client):
        created = create_idle_task()
        task_id = created["task_id"]

        response = app_client.post(
            f"/api/tasks/{task_id}/files",
            files=[
                ("files", ("notes.txt", b"plain text", "text/plain")),
                (
                    "files",
                    (
                        "brief.docx",
                        b"placeholder-docx-bytes",
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    ),
                ),
                (
                    "files",
                    (
                        "data.xlsx",
                        b"placeholder-xlsx-bytes",
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    ),
                ),
                (
                    "files",
                    (
                        "macro.xlsm",
                        b"placeholder-xlsm-bytes",
                        "application/vnd.ms-excel.sheet.macroEnabled.12",
                    ),
                ),
            ],
        )

        assert response.status_code == 201
        events = response.json()["events"]
        uploaded = [event for event in events if event["type"] == "file_uploaded"]
        media_types = {
            event["payload"]["resource_ref"]["name"]: event["payload"]["resource_ref"]["media_type"]
            for event in uploaded
        }
        assert media_types["notes.txt"] == "text"
        assert media_types["brief.docx"] == "word"
        assert media_types["data.xlsx"] == "excel"
        assert media_types["macro.xlsm"] == "excel"

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
            files={"files": ("notes.csv", b"hello", "text/csv")},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "仅支持上传 Markdown、JSON、TXT、DOCX、XLSX 或 XLSM 文件"

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
        client = TestClient(create_app(settings, storage=InMemoryTaskStorage(settings.task_root)))
        created = client.post("/api/tasks", json={"model": "deepseek-v4-flash"}).json()

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
        client = TestClient(create_app(settings, storage=InMemoryTaskStorage(settings.task_root)))
        created = client.post("/api/tasks", json={"model": "deepseek-v4-flash"}).json()

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
