from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import httpx

from .config import Settings


class MemoryServiceError(RuntimeError):
    pass


@dataclass(frozen=True)
class RetrievedMemory:
    id: str
    text: str
    score: float | None = None


class DashScopeEmbeddingClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        dimensions: int,
        timeout_seconds: float = 20.0,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.dimensions = dimensions
        self.timeout_seconds = timeout_seconds

    def embed(self, text: str) -> list[float]:
        payload = {
            "model": self.model,
            "input": text,
            "dimensions": self.dimensions,
            "encoding_format": "float",
        }
        try:
            response = httpx.post(
                f"{self.base_url}/embeddings",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
            embedding = data["data"][0]["embedding"]
        except Exception as exc:
            raise MemoryServiceError("Embedding 服务不可用") from exc
        if not isinstance(embedding, list) or len(embedding) != self.dimensions:
            raise MemoryServiceError("Embedding 服务返回的向量维度不符合配置")
        return [float(item) for item in embedding]


class QdrantMemoryStore:
    def __init__(
        self,
        *,
        url: str,
        collection: str,
        dimensions: int,
        timeout_seconds: float = 20.0,
    ) -> None:
        self.url = url.rstrip("/")
        self.collection = collection
        self.dimensions = dimensions
        self.timeout_seconds = timeout_seconds

    def ensure_collection(self) -> None:
        try:
            response = httpx.get(
                f"{self.url}/collections/{self.collection}",
                timeout=self.timeout_seconds,
            )
            if response.status_code == 404:
                self._create_collection()
                return
            response.raise_for_status()
            self._validate_collection(response.json())
        except MemoryServiceError:
            raise
        except Exception as exc:
            raise MemoryServiceError("Qdrant 服务不可用") from exc

    def _create_collection(self) -> None:
        payload = {
            "vectors": {
                "size": self.dimensions,
                "distance": "Cosine",
            }
        }
        response = httpx.put(
            f"{self.url}/collections/{self.collection}",
            json=payload,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()

    def _validate_collection(self, data: dict[str, Any]) -> None:
        vectors = (
            data.get("result", {})
            .get("config", {})
            .get("params", {})
            .get("vectors")
        )
        if not isinstance(vectors, dict):
            return
        size = vectors.get("size")
        distance = str(vectors.get("distance", "")).lower()
        if size is not None and int(size) != self.dimensions:
            raise MemoryServiceError("Qdrant collection 向量维度不符合配置")
        if distance and distance != "cosine":
            raise MemoryServiceError("Qdrant collection 距离函数不符合配置")

    def upsert(self, *, point_id: str, vector: list[float], payload: dict[str, Any]) -> None:
        try:
            response = httpx.put(
                f"{self.url}/collections/{self.collection}/points",
                params={"wait": "true"},
                json={"points": [{"id": point_id, "vector": vector, "payload": payload}]},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except Exception as exc:
            raise MemoryServiceError("写入 Qdrant 记忆失败") from exc

    def search(self, *, vector: list[float], limit: int) -> list[RetrievedMemory]:
        try:
            response = httpx.post(
                f"{self.url}/collections/{self.collection}/points/search",
                json={"vector": vector, "limit": limit, "with_payload": True},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            items = response.json().get("result", [])
        except Exception as exc:
            raise MemoryServiceError("检索 Qdrant 记忆失败") from exc
        memories: list[RetrievedMemory] = []
        if not isinstance(items, list):
            return memories
        for item in items:
            if not isinstance(item, dict):
                continue
            payload = item.get("payload")
            if not isinstance(payload, dict):
                continue
            text = payload.get("text")
            if isinstance(text, str) and text.strip():
                memories.append(
                    RetrievedMemory(
                        id=str(item.get("id", "")),
                        text=text.strip(),
                        score=float(item["score"]) if isinstance(item.get("score"), (int, float)) else None,
                    )
                )
        return memories


class AgentMemoryService:
    def __init__(self, settings: Settings) -> None:
        if not settings.dashscope_api_key:
            raise MemoryServiceError("DASHSCOPE_API_KEY 未配置")
        if not settings.qdrant_url:
            raise MemoryServiceError("MYAGENT_QDRANT_URL 未配置")
        self.embedding = DashScopeEmbeddingClient(
            api_key=settings.dashscope_api_key,
            base_url=settings.embedding_base_url,
            model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
        )
        self.store = QdrantMemoryStore(
            url=settings.qdrant_url,
            collection=settings.qdrant_collection,
            dimensions=settings.embedding_dimensions,
        )

    def startup_check(self) -> None:
        self.store.ensure_collection()
        self.embedding.embed("MyAgent memory startup probe")

    def recall_context(self, user_message: str, *, limit: int = 3) -> str | None:
        query = user_message.strip()
        if not query:
            return None
        vector = self.embedding.embed(query)
        memories = self.store.search(vector=vector, limit=limit)
        if not memories:
            return None
        lines = [
            "以下是 MyAgent 的本地长期记忆，仅作为背景参考；若与本轮用户输入冲突，以本轮输入为准。"
        ]
        for index, memory in enumerate(memories, start=1):
            lines.append(f"{index}. {memory.text}")
        return "\n".join(lines)

    def remember_completed_run(
        self,
        *,
        task_id: str,
        run_id: str,
        user_goal: str,
        final_answer: str,
    ) -> None:
        text = build_task_memory_text(
            task_id=task_id,
            run_id=run_id,
            user_goal=user_goal,
            final_answer=final_answer,
        )
        vector = self.embedding.embed(text)
        point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"myagent:{task_id}:{run_id}"))
        self.store.upsert(
            point_id=point_id,
            vector=vector,
            payload={
                "schema_version": 1,
                "kind": "completed_task_summary",
                "task_id": task_id,
                "run_id": run_id,
                "text": text,
            },
        )


def build_task_memory_text(*, task_id: str, run_id: str, user_goal: str, final_answer: str) -> str:
    return "\n".join(
        [
            f"用户目标: {_compact(user_goal, 240)}",
            f"最终回答摘要: {_compact(final_answer, 420)}",
            f"任务ID: {task_id}",
            f"运行ID: {run_id}",
        ]
    )


def _compact(text: str, max_chars: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 3].rstrip() + "..."
