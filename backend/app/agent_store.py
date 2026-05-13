from __future__ import annotations

import asyncio
from collections.abc import Iterable
from datetime import datetime, timezone

from langgraph.store.base import (
    BaseStore,
    GetOp,
    Item,
    ListNamespacesOp,
    Op,
    PutOp,
    Result,
    SearchItem,
    SearchOp,
)


class PostgresAgentStore(BaseStore):
    """LangGraph BaseStore backed by MyAgent Postgres task storage."""

    def __init__(self, storage) -> None:
        self.storage = storage

    def batch(self, ops: Iterable[Op]) -> list[Result]:
        results: list[Result] = []
        for op in ops:
            if isinstance(op, GetOp):
                item = self.storage.get_agent_store_item(op.namespace, op.key)
                results.append(_to_item(item) if item is not None else None)
            elif isinstance(op, PutOp):
                if op.value is None:
                    self.storage.delete_agent_store_item(op.namespace, op.key)
                else:
                    self.storage.put_agent_store_item(op.namespace, op.key, op.value)
                results.append(None)
            elif isinstance(op, SearchOp):
                items = self.storage.search_agent_store_items(
                    op.namespace_prefix,
                    filter=op.filter,
                    limit=op.limit,
                    offset=op.offset,
                )
                query = (op.query or "").casefold().strip()
                if query:
                    items = [
                        item
                        for item in items
                        if query in " ".join(str(value) for value in item.value.values()).casefold()
                    ]
                results.append(
                    [
                        SearchItem(
                            namespace=item.namespace,
                            key=item.key,
                            value=item.value,
                            created_at=_parse_time(item.created_at),
                            updated_at=_parse_time(item.updated_at),
                            score=None,
                        )
                        for item in items
                    ]
                )
            elif isinstance(op, ListNamespacesOp):
                prefix = None
                suffix = None
                if op.match_conditions:
                    for condition in op.match_conditions:
                        if condition.match_type == "prefix":
                            prefix = tuple(condition.path)
                        elif condition.match_type == "suffix":
                            suffix = tuple(condition.path)
                results.append(
                    self.storage.list_agent_store_namespaces(
                        prefix=prefix,
                        suffix=suffix,
                        max_depth=op.max_depth,
                        limit=op.limit,
                        offset=op.offset,
                    )
                )
            else:  # pragma: no cover - defensive for future LangGraph operations.
                raise NotImplementedError(f"Unsupported store operation: {type(op).__name__}")
        return results

    async def abatch(self, ops: Iterable[Op]) -> list[Result]:
        return await asyncio.to_thread(self.batch, ops)


def _to_item(item) -> Item:
    return Item(
        namespace=item.namespace,
        key=item.key,
        value=item.value,
        created_at=_parse_time(item.created_at),
        updated_at=_parse_time(item.updated_at),
    )


def _parse_time(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)
