from __future__ import annotations

import pytest

from app.storage import PostgresTaskStorage
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
        state = storage.create_task(message=None, model="deepseek-v4-flash")
        assert state.status == "idle"
        assert state.task_id
        assert state.model == "deepseek-v4-flash"

    def test_create_task_rejects_initial_message(self, tmp_path):
        storage = InMemoryTaskStorage(tmp_path / "sessions")
        try:
            storage.create_task(message="hello", model="deepseek-v4-flash")
        except ValueError:
            pass
        else:
            raise AssertionError("Expected ValueError for initial message")

    def test_create_task_persists_directories(self, tmp_path):
        storage = InMemoryTaskStorage(tmp_path / "sessions")
        state = storage.create_task(message=None, model="deepseek-v4-flash")
        task_dir = storage.task_dir(state.task_id)
        assert sorted(path.name for path in task_dir.iterdir()) == ["uploads"]

    def test_start_run_does_not_create_artifact_directory_before_writes(self, tmp_path):
        storage = InMemoryTaskStorage(tmp_path / "sessions")
        state = storage.create_task(message=None, model="deepseek-v4-flash")

        run_result = storage.start_run(
            state.task_id,
            message="hello",
            model="deepseek-v4-flash",
            expected_statuses={"idle"},
        )

        assert run_result is not None
        task_dir = storage.task_dir(state.task_id)
        assert sorted(path.name for path in task_dir.iterdir()) == ["uploads"]


class TestTaskStorageAppendEvent:
    def test_append_and_read_events(self, tmp_path):
        storage = InMemoryTaskStorage(tmp_path / "sessions")
        state = storage.create_task(message=None, model="deepseek-v4-flash")
        storage.append_event(state.task_id, "test_event", "something happened")
        events = storage.read_events(state.task_id)
        assert any(e.type == "test_event" for e in events)

    def test_read_events_after_known_id_returns_later_events(self, tmp_path):
        storage = InMemoryTaskStorage(tmp_path / "sessions")
        state = storage.create_task(message=None, model="deepseek-v4-flash")
        first = storage.append_event(state.task_id, "first_event", "first")
        second = storage.append_event(state.task_id, "second_event", "second")

        events = storage.read_events(state.task_id, after_id=first.id)

        assert [event.id for event in events] == [second.id]

    def test_read_events_after_unknown_id_recovers_with_full_event_stream(self, tmp_path):
        storage = InMemoryTaskStorage(tmp_path / "sessions")
        state = storage.create_task(message=None, model="deepseek-v4-flash")
        storage.append_event(state.task_id, "test_event", "something happened")

        events = storage.read_events(state.task_id, after_id="missing-event-id")

        assert [event.seq for event in events] == [1, 2]

    def test_large_event_append_keeps_continuous_seq(self, tmp_path):
        storage = InMemoryTaskStorage(tmp_path / "sessions")
        state = storage.create_task(message=None, model="deepseek-v4-flash")
        for index in range(250):
            storage.append_event(state.task_id, "assistant_answer_delta", f"chunk {index}")
        events = storage.read_events(state.task_id)
        assert [event.seq for event in events] == list(range(1, 252))

    def test_read_events_can_filter_specific_run_without_cross_run_leakage(self, tmp_path):
        storage = InMemoryTaskStorage(tmp_path / "sessions")
        state = storage.create_task(message=None, model="deepseek-v4-flash")

        first_run = storage.start_run(
            state.task_id,
            message="first run",
            model="deepseek-v4-flash",
            expected_statuses={"idle"},
        )
        assert first_run is not None
        _, first_run_id = first_run
        first_event = storage.append_event(
            state.task_id,
            "assistant_thinking_delta",
            "first reasoning",
            run_id=first_run_id,
        )
        storage.update_task_if_status(state.task_id, {"running"}, status="complete", run_id=first_run_id)

        second_run = storage.start_run(
            state.task_id,
            message="second run",
            model="deepseek-v4-flash",
            expected_statuses={"complete"},
        )
        assert second_run is not None
        _, second_run_id = second_run
        second_event = storage.append_event(
            state.task_id,
            "assistant_answer_delta",
            "second answer",
            run_id=second_run_id,
        )

        first_run_events = storage.read_events(state.task_id, run_id=first_run_id)
        second_run_events = storage.read_events(state.task_id, run_id=second_run_id)

        assert [event.id for event in first_run_events] == [first_event.id]
        assert [event.run_id for event in first_run_events] == [first_run_id]
        assert [event.id for event in second_run_events] == [second_event.id]
        assert [event.run_id for event in second_run_events] == [second_run_id]

    def test_read_events_run_filter_uses_task_level_after_id_cursor(self, tmp_path):
        storage = InMemoryTaskStorage(tmp_path / "sessions")
        state = storage.create_task(message=None, model="deepseek-v4-flash")

        first_run = storage.start_run(
            state.task_id,
            message="first run",
            model="deepseek-v4-flash",
            expected_statuses={"idle"},
        )
        assert first_run is not None
        _, first_run_id = first_run
        first_event = storage.append_event(
            state.task_id,
            "assistant_thinking_delta",
            "first reasoning",
            run_id=first_run_id,
        )
        storage.update_task_if_status(state.task_id, {"running"}, status="complete", run_id=first_run_id)

        second_run = storage.start_run(
            state.task_id,
            message="second run",
            model="deepseek-v4-flash",
            expected_statuses={"complete"},
        )
        assert second_run is not None
        _, second_run_id = second_run
        second_event = storage.append_event(
            state.task_id,
            "assistant_answer_delta",
            "second answer",
            run_id=second_run_id,
        )

        events = storage.read_events(state.task_id, after_id=first_event.id, run_id=second_run_id)

        assert [event.id for event in events] == [second_event.id]
        assert [event.seq for event in events] == [second_event.seq]

    def test_read_events_rejects_invalid_run_id(self, tmp_path):
        storage = InMemoryTaskStorage(tmp_path / "sessions")
        state = storage.create_task(message=None, model="deepseek-v4-flash")

        with pytest.raises(ValueError, match="运行 ID 无效"):
            storage.read_events(state.task_id, run_id="../invalid")


class TestTaskStorageGetTask:
    def test_get_task_roundtrip(self, tmp_path):
        storage = InMemoryTaskStorage(tmp_path / "sessions")
        state = storage.create_task(message=None, model="deepseek-v4-flash")
        fetched = storage.get_task(state.task_id)
        assert fetched.task_id == state.task_id
        assert fetched.status == "idle"


class TestTaskStorageHistoryActions:
    def test_rename_task_sets_custom_title(self, tmp_path):
        storage = InMemoryTaskStorage(tmp_path / "sessions")
        state = storage.create_task(message=None, model="deepseek-v4-flash")

        renamed = storage.rename_task(state.task_id, "  新标题  ")

        assert renamed.title == "新标题"

    def test_set_task_title_if_empty_only_sets_blank_title(self, tmp_path):
        storage = InMemoryTaskStorage(tmp_path / "sessions")
        state = storage.create_task(message=None, model="deepseek-v4-flash")

        titled = storage.set_task_title_if_empty(state.task_id, "  自动标题  ")
        preserved = storage.set_task_title_if_empty(state.task_id, "另一个标题")

        assert titled.title == "自动标题"
        assert preserved.title == "自动标题"

    def test_delete_task_removes_state_and_files(self, tmp_path):
        storage = InMemoryTaskStorage(tmp_path / "sessions")
        state = storage.create_task(message=None, model="deepseek-v4-flash")
        task_dir = storage.task_dir(state.task_id)

        storage.delete_task(state.task_id)

        assert not task_dir.exists()
        try:
            storage.get_task(state.task_id)
        except FileNotFoundError:
            pass
        else:
            raise AssertionError("Expected deleted task to be missing")


class TestPostgresTaskStorageRunArtifacts:
    def test_write_run_text_records_custom_run_artifact_without_database(self, tmp_path, monkeypatch):
        storage = PostgresTaskStorage(tmp_path / "sessions", "postgresql://unused")
        task_id = "task-1"
        run_id = "run-test-001"
        recorded: list[tuple[str, str, str, dict | None]] = []

        def record_run_artifact(task_id_arg, run_id_arg, artifact_name_arg, *, artifact_ref=None):
            recorded.append((task_id_arg, run_id_arg, artifact_name_arg, artifact_ref))

        monkeypatch.setattr(storage, "record_run_artifact", record_run_artifact)

        path = storage.write_run_text(task_id, run_id, "analysis-extra.json", '{"ok": true}')

        assert path == (
            tmp_path
            / "sessions"
            / task_id
            / "artifacts"
            / "runs"
            / run_id
            / "analysis-extra.json"
        ).resolve()
        assert path.read_text(encoding="utf-8") == '{"ok": true}'
        assert len(recorded) == 1
        recorded_task_id, recorded_run_id, recorded_name, artifact_ref = recorded[0]
        assert recorded_task_id == task_id
        assert recorded_run_id == run_id
        assert recorded_name == "analysis-extra.json"
        assert artifact_ref is not None
        assert artifact_ref["id"] == "artifact:task-1:run-test-001:analysis-extra.json"
        assert artifact_ref["name"] == "analysis-extra.json"
        assert artifact_ref["type"] == "json"
        assert artifact_ref["uri"] == (
            "myagent://sessions/task-1/runs/run-test-001/artifacts/analysis-extra.json"
        )
        assert artifact_ref["run_id"] == run_id
        assert artifact_ref["size_bytes"] == 12
        assert artifact_ref["digest"] == (
            "sha256:6bc0da1f42f96fc37b8bd7ed20ba57606d2a0da5cda2b135c7854fbdc985b8a3"
        )
        assert artifact_ref["resource_ref"]["kind"] == "artifact"
        assert artifact_ref["resource_ref"]["name"] == "analysis-extra.json"

    def test_write_run_text_keeps_top_level_mirror_for_fixed_artifacts(self, tmp_path, monkeypatch):
        storage = PostgresTaskStorage(tmp_path / "sessions", "postgresql://unused")
        task_id = "task-1"
        run_id = "run-test-001"
        recorded: list[str] = []

        def record_run_artifact(_task_id, _run_id, artifact_name, *, artifact_ref=None):
            recorded.append(artifact_name)

        monkeypatch.setattr(storage, "record_run_artifact", record_run_artifact)

        storage.write_run_text(task_id, run_id, "report.html", "<h1>报告</h1>")

        mirrored = tmp_path / "sessions" / task_id / "artifacts" / "report.html"
        assert mirrored.read_text(encoding="utf-8") == "<h1>报告</h1>"
        assert recorded == ["report.html"]

    def test_write_run_manifest_stays_inside_run_artifacts_dir(self, tmp_path):
        storage = PostgresTaskStorage(tmp_path / "sessions", "postgresql://unused")
        task_id = "task-1"
        run_id = "run-test-001"

        path = storage.write_run_manifest(task_id, run_id, {"ok": True})

        assert path == (
            tmp_path / "sessions" / task_id / "artifacts" / "runs" / run_id / "run.json"
        ).resolve()
        assert path.read_text(encoding="utf-8") == '{\n  "ok": true\n}'
        assert sorted(child.name for child in (tmp_path / "sessions" / task_id).iterdir()) == [
            "artifacts"
        ]
