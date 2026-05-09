from __future__ import annotations

from app.storage import TaskStorage


class TestTaskStorageInit:
    def test_creates_task_root(self, tmp_path):
        root = tmp_path / "sessions"
        TaskStorage(root)
        assert root.is_dir()

    def test_task_dir_returns_valid_path(self, tmp_path):
        storage = TaskStorage(tmp_path / "sessions")
        result = storage.task_dir("abc-123")
        assert result == (tmp_path / "sessions" / "abc-123").resolve()

    def test_task_dir_rejects_traversal(self, tmp_path):
        storage = TaskStorage(tmp_path / "sessions")
        try:
            storage.task_dir("..")
        except ValueError:
            pass
        else:
            raise AssertionError("Expected ValueError for path traversal")


class TestTaskStorageCreateTask:
    def test_create_task_returns_idle_state(self, tmp_path):
        storage = TaskStorage(tmp_path / "sessions")
        state = storage.create_task(message=None, model="deepseek:deepseek-chat")
        assert state.status == "idle"
        assert state.task_id
        assert state.model == "deepseek:deepseek-chat"

    def test_create_task_rejects_initial_message(self, tmp_path):
        storage = TaskStorage(tmp_path / "sessions")
        try:
            storage.create_task(message="hello", model="deepseek:deepseek-chat")
        except ValueError:
            pass
        else:
            raise AssertionError("Expected ValueError for initial message")

    def test_create_task_persists_directories(self, tmp_path):
        storage = TaskStorage(tmp_path / "sessions")
        state = storage.create_task(message=None, model="deepseek:deepseek-chat")
        task_dir = storage.task_dir(state.task_id)
        assert (task_dir / "uploads").is_dir()
        assert (task_dir / "artifacts").is_dir()


class TestTaskStorageAppendEvent:
    def test_append_and_read_events(self, tmp_path):
        storage = TaskStorage(tmp_path / "sessions")
        state = storage.create_task(message=None, model="deepseek:deepseek-chat")
        storage.append_event(state.task_id, "test_event", "something happened")
        events = storage.read_events(state.task_id)
        assert any(e.type == "test_event" for e in events)


class TestTaskStorageGetTask:
    def test_get_task_roundtrip(self, tmp_path):
        storage = TaskStorage(tmp_path / "sessions")
        state = storage.create_task(message=None, model="deepseek:deepseek-chat")
        fetched = storage.get_task(state.task_id)
        assert fetched.task_id == state.task_id
        assert fetched.status == "idle"
