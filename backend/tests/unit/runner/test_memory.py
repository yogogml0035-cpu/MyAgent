from __future__ import annotations

from typing import Any, cast

from app.memory import (
    AgentMemoryService,
    ExtractedMemory,
    QdrantMemoryIndex,
    build_task_memory_text,
    parse_memory_extraction,
)
from app.security.scanner import scan_text_for_secrets
from app.storage import LongTermMemoryRecord


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


class _FakeIndex:
    def __init__(self) -> None:
        self.upserts: list[dict[str, Any]] = []
        self.reset_count = 0

    def reset_collection(self) -> None:
        self.reset_count += 1

    def upsert(self, *, point_id: str, vector: list[float], payload: dict[str, Any]) -> None:
        self.upserts.append({"point_id": point_id, "vector": vector, "payload": payload})

    def search(self, *, vector: list[float], user_id: str, limit: int):
        return []


class _FakeStorage:
    def __init__(self) -> None:
        self.memories: list[dict[str, Any]] = []

    def put_long_term_memory(self, **kwargs):
        self.memories.append(kwargs)

    def list_long_term_memories(self, *, limit: int = 1000, offset: int = 0, user_id: str | None = None):
        return []


def test_parse_memory_extraction_accepts_only_whitelisted_structured_memories():
    parsed = parse_memory_extraction(
        """
        ```json
        {"memories":[
          {"type":"preference","text":"用户喜欢先确认边界","confidence":0.91},
          {"type":"temporary_fact","text":"今天上海下雨","confidence":0.99},
          {"type":"stable_workflow","text":"架构任务先拆职责和接口","confidence":0.73}
        ]}
        ```
        """
    )

    assert parsed == [
        ExtractedMemory("preference", "用户喜欢先确认边界", 0.91),
        ExtractedMemory("stable_workflow", "架构任务先拆职责和接口", 0.73),
    ]


def test_remember_completed_run_persists_canonical_memory_and_qdrant_index(monkeypatch):
    service = cast(Any, object.__new__(AgentMemoryService))
    embedding = _FakeEmbedding()
    index = _FakeIndex()
    storage = _FakeStorage()
    service.embedding = embedding
    service.index = index
    service.storage = storage
    service.settings = type(
        "Settings",
        (),
        {
            "default_user_id": "user-1",
            "default_model": "deepseek-v4-flash",
            "memory_min_score": 0.7,
        },
    )()
    monkeypatch.setattr(
        service,
        "extract_memories",
        lambda **_: [
            ExtractedMemory("preference", "用户喜欢先确认架构边界", 0.92),
            ExtractedMemory("stable_workflow", "低置信度不保存", 0.3),
        ],
    )

    ids = service.remember_completed_run(  # ggignore
        task_id="task-1",
        run_id="run-1",
        user_goal="处理客户文档 SECRET_DOC_CANARY_demo_123",
        final_answer="需要设置 DASHSCOPE_API_KEY=not_a_real_key",
        user_id="user-1",
    )

    assert len(ids) == 1
    assert len(storage.memories) == 1
    assert storage.memories[0]["user_id"] == "user-1"
    assert storage.memories[0]["memory_type"] == "preference"
    assert len(index.upserts) == 1
    payload = index.upserts[0]["payload"]
    assert payload["schema_version"] == 2
    assert payload["kind"] == "long_term_memory"
    assert payload["user_id"] == "user-1"
    assert embedding.inputs == ["用户喜欢先确认架构边界"]
    assert scan_text_for_secrets(payload["text"], source="memory") == []


def test_rebuild_index_from_canonical_storage_recreates_schema_v2_points():
    service = cast(Any, object.__new__(AgentMemoryService))
    embedding = _FakeEmbedding()
    index = _FakeIndex()

    class Storage:
        def __init__(self) -> None:
            self.records = [
                LongTermMemoryRecord(
                    memory_id="memory-1",
                    user_id="user-1",
                    memory_type="preference",
                    text="用户喜欢先确认架构边界",
                    confidence=0.93,
                    source_task_id="task-1",
                    source_run_id="run-1",
                    created_at="2025-01-01T00:00:00Z",
                    updated_at="2025-01-01T00:00:00Z",
                )
            ]

        def list_long_term_memories(
            self, *, limit: int = 1000, offset: int = 0, user_id: str | None = None
        ):
            return self.records[offset : offset + limit]

    service.embedding = embedding
    service.index = index
    service.storage = Storage()

    count = service.rebuild_index_from_storage(batch_size=1)

    assert count == 1
    assert index.reset_count == 1
    payload = index.upserts[0]["payload"]
    assert payload["schema_version"] == 2
    assert payload["memory_id"] == "memory-1"
    assert payload["user_id"] == "user-1"


def test_qdrant_reset_recreates_only_configured_collection(monkeypatch):
    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    class Response:
        status_code = 200

        def raise_for_status(self):
            return None

    def fake_delete(url: str, timeout: float):
        calls.append(("DELETE", url, None))
        return Response()

    def fake_put(url: str, json: dict[str, Any], timeout: float):
        calls.append(("PUT", url, json))
        return Response()

    monkeypatch.setattr("app.memory.httpx.delete", fake_delete)
    monkeypatch.setattr("app.memory.httpx.put", fake_put)

    QdrantMemoryIndex(
        url="http://qdrant:6333",
        collection="myagent_memories_test",
        dimensions=1024,
    ).reset_collection()

    assert calls == [
        ("DELETE", "http://qdrant:6333/collections/myagent_memories_test", None),
        (
            "PUT",
            "http://qdrant:6333/collections/myagent_memories_test",
            {"vectors": {"size": 1024, "distance": "Cosine"}},
        ),
    ]
