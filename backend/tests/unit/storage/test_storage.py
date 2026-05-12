from __future__ import annotations

from tests.fakes import InMemoryTaskStorage


class TestTaskStorageInit:
    def test_creates_task_root(self, tmp_path):
        root = tmp_path / "sessions"
        InMemoryTaskStorage(root)
        assert root.is_dir()

    def test_task_dir_returns_valid_path(self, tmp_path):
        storage = InMemoryTaskStorage(tmp_path / "sessions")
        result = storage.task_dir("abc-123")
        assert result == (tmp_path / "sessions" / "abc-123").resolve()

    def test_task_dir_rejects_traversal(self, tmp_path):
        storage = InMemoryTaskStorage(tmp_path / "sessions")
        try:
            storage.task_dir("..")
        except ValueError:
            pass
        else:
            raise AssertionError("Expected ValueError for path traversal")


class TestTaskStorageCreateTask:
    def test_create_task_returns_idle_state(self, tmp_path):
        storage = InMemoryTaskStorage(tmp_path / "sessions")
        state = storage.create_task(message=None, model="deepseek:deepseek-chat")
        assert state.status == "idle"
        assert state.task_id
        assert state.model == "deepseek:deepseek-chat"

    def test_create_task_rejects_initial_message(self, tmp_path):
        storage = InMemoryTaskStorage(tmp_path / "sessions")
        try:
            storage.create_task(message="hello", model="deepseek:deepseek-chat")
        except ValueError:
            pass
        else:
            raise AssertionError("Expected ValueError for initial message")

    def test_create_task_persists_directories(self, tmp_path):
        storage = InMemoryTaskStorage(tmp_path / "sessions")
        state = storage.create_task(message=None, model="deepseek:deepseek-chat")
        task_dir = storage.task_dir(state.task_id)
        assert (task_dir / "uploads").is_dir()
        assert (task_dir / "artifacts").is_dir()


class TestTaskStorageAppendEvent:
    def test_append_and_read_events(self, tmp_path):
        storage = InMemoryTaskStorage(tmp_path / "sessions")
        state = storage.create_task(message=None, model="deepseek:deepseek-chat")
        storage.append_event(state.task_id, "test_event", "something happened")
        events = storage.read_events(state.task_id)
        assert any(e.type == "test_event" for e in events)

    def test_large_event_append_keeps_continuous_seq(self, tmp_path):
        storage = InMemoryTaskStorage(tmp_path / "sessions")
        state = storage.create_task(message=None, model="deepseek:deepseek-chat")
        for index in range(250):
            storage.append_event(state.task_id, "assistant_answer_delta", f"chunk {index}")
        events = storage.read_events(state.task_id)
        assert [event.seq for event in events] == list(range(1, 252))


class TestTaskStorageGetTask:
    def test_get_task_roundtrip(self, tmp_path):
        storage = InMemoryTaskStorage(tmp_path / "sessions")
        state = storage.create_task(message=None, model="deepseek:deepseek-chat")
        fetched = storage.get_task(state.task_id)
        assert fetched.task_id == state.task_id
        assert fetched.status == "idle"


class TestTaskStorageHistoryActions:
    def test_rename_task_sets_custom_title(self, tmp_path):
        storage = InMemoryTaskStorage(tmp_path / "sessions")
        state = storage.create_task(message=None, model="deepseek:deepseek-chat")

        renamed = storage.rename_task(state.task_id, "  新标题  ")

        assert renamed.title == "新标题"

    def test_delete_task_removes_state_and_files(self, tmp_path):
        storage = InMemoryTaskStorage(tmp_path / "sessions")
        state = storage.create_task(message=None, model="deepseek:deepseek-chat")
        task_dir = storage.task_dir(state.task_id)

        storage.delete_task(state.task_id)

        assert not task_dir.exists()
        try:
            storage.get_task(state.task_id)
        except FileNotFoundError:
            pass
        else:
            raise AssertionError("Expected deleted task to be missing")
