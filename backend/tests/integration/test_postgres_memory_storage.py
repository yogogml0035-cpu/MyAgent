from __future__ import annotations

import os
from typing import Any, cast

import pytest

from app.config import Settings
from app.memory import AgentMemoryService, ExtractedMemory
from app.storage import PostgresTaskStorage


class _FakeEmbedding:
    def __init__(self, dimensions: int) -> None:
        self.dimensions = dimensions
        self.inputs: list[str] = []

    def embed(self, text: str) -> list[float]:
        self.inputs.append(text)
        return [0.01] * self.dimensions


def _is_placeholder(value: str | None) -> bool:
    if not value:
        return True
    markers = ("USER", "PASSWORD", "DBNAME", "your-", "xxx", "example")
    return any(marker in value for marker in markers)


def _database_url() -> str | None:
    value = os.getenv("MYAGENT_TEST_DATABASE_URL") or os.getenv("MYAGENT_DATABASE_URL")
    return None if _is_placeholder(value) else value


@pytest.mark.skipif(not _database_url(), reason="Postgres integration env is not configured")
def test_postgres_event_seq_survives_storage_reinstantiation(tmp_path):
    database_url = _database_url()
    assert database_url is not None
    storage = PostgresTaskStorage(tmp_path / "tasks", database_url)
    storage.initialize()
    state = storage.create_task(message=None, model="deepseek-v4-flash")
    for index in range(50):
        storage.append_event(state.task_id, "assistant_answer_delta", f"chunk {index}")

    restarted = PostgresTaskStorage(tmp_path / "tasks", database_url)
    restarted.initialize()
    restarted.append_event(state.task_id, "final_answer", "done")

    events = restarted.read_events(state.task_id)
    assert [event.seq for event in events] == list(range(1, 53))


@pytest.mark.skipif(not _database_url(), reason="Postgres integration env is not configured")
def test_postgres_rename_and_delete_task(tmp_path):
    database_url = _database_url()
    assert database_url is not None
    storage = PostgresTaskStorage(tmp_path / "tasks", database_url)
    storage.initialize()
    state = storage.create_task(message=None, model="deepseek-v4-flash")

    renamed = storage.rename_task(state.task_id, "  历史菜单验收  ")

    assert renamed.title == "历史菜单验收"
    storage.delete_task(state.task_id)
    with pytest.raises(FileNotFoundError):
        storage.get_task(state.task_id)


def _memory_env_ready() -> bool:
    return not _is_placeholder(os.getenv("MYAGENT_QDRANT_URL")) and not _is_placeholder(
        os.getenv("DASHSCOPE_API_KEY")
    )


@pytest.mark.skipif(
    not (_database_url() and _memory_env_ready()),
    reason="Qdrant/DashScope integration env is not configured",
)
def test_memory_service_writes_and_recalls_completed_task_memory_v2(tmp_path, monkeypatch):
    settings = Settings(
        task_root=tmp_path / "tasks",
        workspace_root=tmp_path / "tasks",
        database_url=_database_url(),
        qdrant_url=os.getenv("MYAGENT_QDRANT_URL"),
        dashscope_api_key=os.getenv("DASHSCOPE_API_KEY"),
        default_user_id="integration-user",
    )
    storage = PostgresTaskStorage(settings.task_root, settings.database_url or "")
    storage.initialize()
    state = storage.create_task(message=None, model="deepseek-v4-flash")
    run = storage.start_run(
        state.task_id,
        message="记住我喜欢先做架构边界再写实现",
        model="deepseek-v4-flash",
        expected_statuses={"idle"},
    )
    assert run is not None
    _, run_id = run
    service = AgentMemoryService(settings, storage)
    service.embedding = cast(Any, _FakeEmbedding(settings.embedding_dimensions))
    service.startup_check()
    monkeypatch.setattr(
        service,
        "extract_memories",
        lambda **_: [ExtractedMemory("preference", "用户喜欢先做架构边界再写实现", 0.94)],
    )
    service.remember_completed_run(
        task_id=state.task_id,
        run_id=run_id,
        user_goal="记住我喜欢先做架构边界再写实现",
        final_answer="后续同类任务会先明确存储边界、失败策略和测试入口。",
        user_id="integration-user",
    )

    context = service.recall_context("我喜欢先做架构边界再写实现", user_id="integration-user")

    assert context is not None
    assert "长期记忆" in context
    assert "架构边界" in context
