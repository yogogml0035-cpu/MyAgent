from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from langchain_core.messages import HumanMessage, SystemMessage

from .config import Settings
from .models.provider import create_model
from .security.scanner import SENSITIVE_REDACTION, redact_sensitive_text, scan_text_for_secrets

logger = logging.getLogger(__name__)

MEMORY_TYPES = {"preference", "profile_fact", "project_rule", "stable_workflow"}


class MemoryServiceError(RuntimeError):
    pass


@dataclass(frozen=True)
class RetrievedMemory:
    id: str
    text: str
    memory_type: str | None = None
    score: float | None = None


@dataclass(frozen=True)
class ExtractedMemory:
    memory_type: str
    text: str
    confidence: float


class LongTermMemoryStorage(Protocol):
    def put_long_term_memory(
        self,
        *,
        memory_id: str,
        user_id: str,
        memory_type: str,
        text: str,
        confidence: float,
        source_task_id: str,
        source_run_id: str,
    ) -> Any: ...

    def get_long_term_memory(self, memory_id: str) -> Any | None: ...

    def list_long_term_memories(
        self, *, limit: int = 1000, offset: int = 0, user_id: str | None = None
    ) -> list[Any]: ...


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


class QdrantMemoryIndex:
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

    def reset_collection(self) -> None:
        try:
            response = httpx.delete(
                f"{self.url}/collections/{self.collection}",
                timeout=self.timeout_seconds,
            )
            if response.status_code not in {200, 202, 404}:
                response.raise_for_status()
            self._create_collection()
        except Exception as exc:
            raise MemoryServiceError("重建 Qdrant 记忆 collection 失败") from exc

    def _create_collection(self) -> None:
        payload = {"vectors": {"size": self.dimensions, "distance": "Cosine"}}
        response = httpx.put(
            f"{self.url}/collections/{self.collection}",
            json=payload,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()

    def _validate_collection(self, data: dict[str, Any]) -> None:
        vectors = data.get("result", {}).get("config", {}).get("params", {}).get("vectors")
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
            raise MemoryServiceError("写入 Qdrant 记忆索引失败") from exc

    def search(self, *, vector: list[float], user_id: str, limit: int) -> list[RetrievedMemory]:
        try:
            response = httpx.post(
                f"{self.url}/collections/{self.collection}/points/search",
                json={
                    "vector": vector,
                    "limit": limit,
                    "with_payload": True,
                    "filter": {"must": [{"key": "user_id", "match": {"value": user_id}}]},
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            items = response.json().get("result", [])
        except Exception as exc:
            raise MemoryServiceError("检索 Qdrant 记忆索引失败") from exc
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
            memory_id = payload.get("memory_id") or item.get("id")
            if isinstance(text, str) and text.strip():
                memories.append(
                    RetrievedMemory(
                        id=str(memory_id),
                        text=text.strip(),
                        memory_type=str(payload.get("memory_type") or ""),
                        score=float(item["score"]) if isinstance(item.get("score"), (int, float)) else None,
                    )
                )
        return memories


class AgentMemoryService:
    def __init__(self, settings: Settings, storage: LongTermMemoryStorage | None = None) -> None:
        if not settings.dashscope_api_key:
            raise MemoryServiceError("DASHSCOPE_API_KEY 未配置")
        if not settings.qdrant_url:
            raise MemoryServiceError("MYAGENT_QDRANT_URL 未配置")
        self.settings = settings
        self.storage = storage
        self.embedding = DashScopeEmbeddingClient(
            api_key=settings.dashscope_api_key,
            base_url=settings.embedding_base_url,
            model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
        )
        self.index = QdrantMemoryIndex(
            url=settings.qdrant_url,
            collection=settings.qdrant_collection,
            dimensions=settings.embedding_dimensions,
        )

    def startup_check(self) -> None:
        self.index.ensure_collection()
        self.embedding.embed("MyAgent memory startup probe")

    def reset_index(self) -> None:
        self.index.reset_collection()

    def rebuild_index_from_storage(self, *, batch_size: int = 500) -> int:
        if self.storage is None:
            return 0
        self.index.reset_collection()
        indexed = 0
        offset = 0
        while True:
            records = self.storage.list_long_term_memories(limit=batch_size, offset=offset)
            if not records:
                break
            for record in records:
                text = _sanitize_memory_segment(str(record.text), max_chars=420)
                if not text or _has_sensitive_memory_content(text):
                    continue
                self._upsert_memory_index(
                    memory_id=str(record.memory_id),
                    user_id=str(record.user_id),
                    memory_type=str(record.memory_type),
                    text=text,
                    confidence=float(record.confidence),
                    source_task_id=str(record.source_task_id),
                    source_run_id=str(record.source_run_id),
                )
                indexed += 1
            offset += len(records)
        return indexed

    def recall_context(
        self, user_message: str, *, user_id: str | None = None, limit: int = 3
    ) -> str | None:
        if _has_sensitive_memory_content(user_message):
            logger.info("Skipping long-term memory recall for sensitive user input")
            return None
        query = _compact(redact_sensitive_text(user_message), 420)
        if not query:
            return None
        resolved_user_id = user_id or self.settings.default_user_id
        vector = self.embedding.embed(query)
        memories = self.index.search(vector=vector, user_id=resolved_user_id, limit=limit)
        if not memories:
            return None
        memory_lines: list[str] = []
        for index, memory in enumerate(memories, start=1):
            if memory.score is not None and memory.score < self.settings.memory_min_score:
                continue
            memory_text = _sanitize_memory_segment(memory.text, max_chars=520)
            if memory_text:
                label = f"{memory.memory_type}: " if memory.memory_type else ""
                memory_lines.append(f"{index}. {label}{memory_text}")
        if not memory_lines:
            return None
        lines = [
            "以下是 MyAgent 的本地长期记忆，仅作为背景参考；若与本轮用户输入冲突，以本轮输入为准。"
        ]
        lines.extend(memory_lines)
        return "\n".join(lines)

    def recall_event_payload(
        self, context: str | None, *, user_id: str | None = None
    ) -> dict[str, Any] | None:
        if not context:
            return None
        lines = [line for line in context.splitlines()[1:] if line.strip()]
        return {
            "schema_version": 1,
            "user_id": user_id or self.settings.default_user_id,
            "memory_count": len(lines),
            "memory_previews": [_compact(line, 180) for line in lines[:3]],
            "live": {
                "schema_version": 1,
                "kind": "status",
                "stage": "organizing_state",
                "display_text": "已载入长期记忆",
                "diagnostic_label": "long_term_memory",
                "parameter_items": [
                    {"key": "用户", "value": user_id or self.settings.default_user_id},
                    {"key": "记忆数", "value": len(lines)},
                ],
            },
        }

    def remember_completed_run(
        self,
        *,
        task_id: str,
        run_id: str,
        user_goal: str,
        final_answer: str,
        user_id: str | None = None,
        model: str | None = None,
    ) -> list[str]:
        if not hasattr(self, "storage") or self.storage is None:
            return []
        resolved_user_id = user_id or self.settings.default_user_id
        memories = self.extract_memories(
            user_goal=user_goal,
            final_answer=final_answer,
            model=model or self.settings.default_model,
        )
        memory_ids: list[str] = []
        for memory in memories:
            if memory.confidence < self.settings.memory_min_score:
                continue
            text = _sanitize_memory_segment(memory.text, max_chars=420)
            if not text or _has_sensitive_memory_content(text):
                continue
            memory_id = str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"myagent-memory-v2:{resolved_user_id}:{memory.memory_type}:{text}",
                )
            )
            self.storage.put_long_term_memory(
                memory_id=memory_id,
                user_id=resolved_user_id,
                memory_type=memory.memory_type,
                text=text,
                confidence=memory.confidence,
                source_task_id=task_id,
                source_run_id=run_id,
            )
            self._upsert_memory_index(
                memory_id=memory_id,
                user_id=resolved_user_id,
                memory_type=memory.memory_type,
                text=text,
                confidence=memory.confidence,
                source_task_id=task_id,
                source_run_id=run_id,
            )
            memory_ids.append(memory_id)
        return memory_ids

    def _upsert_memory_index(
        self,
        *,
        memory_id: str,
        user_id: str,
        memory_type: str,
        text: str,
        confidence: float,
        source_task_id: str,
        source_run_id: str,
    ) -> None:
        vector = self.embedding.embed(text)
        self.index.upsert(
            point_id=memory_id,
            vector=vector,
            payload={
                "schema_version": 2,
                "kind": "long_term_memory",
                "user_id": user_id,
                "memory_id": memory_id,
                "memory_type": memory_type,
                "text": text,
                "confidence": confidence,
                "source_task_id": source_task_id,
                "source_run_id": source_run_id,
            },
        )

    def extract_memories(self, *, user_goal: str, final_answer: str, model: str) -> list[ExtractedMemory]:
        prompt = (
            "从本轮对话中抽取值得跨会话长期保存的用户记忆。只允许保存用户偏好、用户稳定事实、"
            "项目长期规则、稳定工作方式。不要保存普通问答、天气新闻价格等临时事实、上传原文、"
            "工具日志、密钥或敏感内容。返回 JSON：{\"memories\":[{\"type\":\"preference|profile_fact|project_rule|stable_workflow\",\"text\":\"短句\",\"confidence\":0.0-1.0}]}。"
        )
        source = json.dumps(
            {
                "user_goal": _sanitize_memory_segment(user_goal, max_chars=900),
                "final_answer": _sanitize_memory_segment(final_answer, max_chars=1200),
            },
            ensure_ascii=False,
        )
        try:
            chat_model = create_model(model, settings=self.settings, temperature=0.0)
            response = chat_model.invoke(
                [SystemMessage(content=prompt), HumanMessage(content=source)]
            )
            content = getattr(response, "content", "")
        except Exception:
            logger.warning("Long-term memory extraction failed", exc_info=True)
            return []
        return parse_memory_extraction(content)


def parse_memory_extraction(content: Any) -> list[ExtractedMemory]:
    text = _extract_text_content(content).strip()
    if not text:
        return []
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return []
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return []
    raw_memories = data.get("memories") if isinstance(data, dict) else None
    if not isinstance(raw_memories, list):
        return []
    memories: list[ExtractedMemory] = []
    for item in raw_memories[:8]:
        if not isinstance(item, dict):
            continue
        memory_type = str(item.get("type") or item.get("memory_type") or "")
        text_value = _compact(str(item.get("text") or ""), 420)
        confidence = item.get("confidence", 0)
        if memory_type not in MEMORY_TYPES or not text_value:
            continue
        if not isinstance(confidence, (int, float)):
            continue
        memories.append(
            ExtractedMemory(
                memory_type=memory_type,
                text=text_value,
                confidence=max(0.0, min(float(confidence), 1.0)),
            )
        )
    return memories


def build_task_memory_text(*, task_id: str, run_id: str, user_goal: str, final_answer: str) -> str:
    return "\n".join(
        [
            f"用户目标: {_sanitize_memory_segment(user_goal, max_chars=240)}",
            f"最终回答摘要: {_sanitize_memory_segment(final_answer, max_chars=420)}",
            f"任务ID: {task_id}",
            f"运行ID: {run_id}",
        ]
    )


def _extract_text_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            item.get("text", "") if isinstance(item, dict) else str(item) for item in content
        )
    return str(content)


def _sanitize_memory_segment(text: str, *, max_chars: int) -> str:
    sanitized = redact_sensitive_text(text)
    compact = _compact(sanitized, max_chars)
    if _has_sensitive_memory_content(compact):
        return SENSITIVE_REDACTION
    return compact


def _has_sensitive_memory_content(text: str) -> bool:
    return bool(scan_text_for_secrets(text, source="memory"))


def _compact(text: str, max_chars: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 3].rstrip() + "..."
