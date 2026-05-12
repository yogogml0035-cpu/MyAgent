from __future__ import annotations

from typing import Any, cast

from app.memory import AgentMemoryService, build_task_memory_text
from app.security.scanner import scan_text_for_secrets


def test_build_task_memory_text_is_high_level_and_bounded():
    text = build_task_memory_text(
        task_id="task-1",
        run_id="run-1",
        user_goal="请帮我分析一个很长的目标" * 50,
        final_answer="这是最终回答" * 80,
    )

    assert "用户目标:" in text
    assert "最终回答摘要:" in text
    assert "task-1" in text
    assert len(text) < 800


def test_build_task_memory_text_redacts_sensitive_material():
    text = build_task_memory_text(  # ggignore
        task_id="task-1",
        run_id="run-1",
        user_goal="请分析 Authorization: Bearer not_a_real_token_999 的问题",
        final_answer=(
            "最终结论包含 api_key=sk-00000000FAKE00000000000000 "
            "和客户原文 SECRET_DOC_CANARY_demo_123"
        ),
    )

    assert "Authorization" not in text
    assert "Bearer" not in text
    assert "api_key" not in text
    assert "SECRET_DOC_CANARY" not in text
    assert scan_text_for_secrets(text, source="memory") == []


class _FakeEmbedding:
    def __init__(self) -> None:
        self.inputs: list[str] = []

    def embed(self, text: str) -> list[float]:
        self.inputs.append(text)
        return [0.1, 0.2]


class _FakeStore:
    def __init__(self) -> None:
        self.upserts: list[dict[str, Any]] = []

    def upsert(self, *, point_id: str, vector: list[float], payload: dict[str, Any]) -> None:
        self.upserts.append({"point_id": point_id, "vector": vector, "payload": payload})


def test_remember_completed_run_only_persists_sanitized_summary():
    service = cast(Any, object.__new__(AgentMemoryService))
    embedding = _FakeEmbedding()
    store = _FakeStore()
    service.embedding = embedding
    service.store = store

    service.remember_completed_run(  # ggignore
        task_id="task-1",
        run_id="run-1",
        user_goal="处理客户文档 SECRET_DOC_CANARY_demo_123",
        final_answer="需要设置 DASHSCOPE_API_KEY=not_a_real_key",
    )

    assert len(store.upserts) == 1
    memory_text = store.upserts[0]["payload"]["text"]
    assert embedding.inputs == [memory_text]
    assert "SECRET_DOC_CANARY" not in memory_text
    assert "DASHSCOPE_API_KEY" not in memory_text
    assert scan_text_for_secrets(memory_text, source="memory") == []
