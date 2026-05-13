from __future__ import annotations

from app.agent_store import PostgresAgentStore
from tests.fakes import InMemoryTaskStorage


def test_postgres_agent_store_round_trips_items(tmp_path):
    storage = InMemoryTaskStorage(tmp_path / "tasks")
    store = PostgresAgentStore(storage)

    store.put(("users", "user-1", "filesystem"), "preferences.txt", {"content": "先确认边界"})

    item = store.get(("users", "user-1", "filesystem"), "preferences.txt")
    assert item is not None
    assert item.value["content"] == "先确认边界"

    results = store.search(("users", "user-1"))
    assert [result.key for result in results] == ["preferences.txt"]

    namespaces = store.list_namespaces(prefix=("users",), max_depth=2)
    assert namespaces == [("users", "user-1")]

    store.delete(("users", "user-1", "filesystem"), "preferences.txt")
    assert store.get(("users", "user-1", "filesystem"), "preferences.txt") is None


def test_postgres_agent_store_applies_filter_before_pagination(tmp_path):
    storage = InMemoryTaskStorage(tmp_path / "tasks")
    store = PostgresAgentStore(storage)

    store.put(("users", "user-1", "filesystem"), "a.txt", {"type": "skip", "content": "a"})
    store.put(("users", "user-1", "filesystem"), "b.txt", {"type": "keep", "content": "b"})
    store.put(("users", "user-1", "filesystem"), "c.txt", {"type": "keep", "content": "c"})

    results = store.search(("users", "user-1"), filter={"type": "keep"}, limit=1)

    assert [result.key for result in results] == ["b.txt"]
