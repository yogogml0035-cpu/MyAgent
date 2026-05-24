from __future__ import annotations

import asyncio
import inspect
import threading
from collections.abc import AsyncIterator
from typing import Any, Literal

import pytest
from langchain_core.messages import AIMessage, SystemMessage

from app.memory import MemoryServiceError
from app.runner.core import TaskRunner
from app.schemas import EventRecord
from tests.fakes import InMemoryTaskStorage


class TestTaskRunnerInit:
    def test_init_stores_settings(self, test_settings):
        runner = TaskRunner(test_settings)
        assert runner.settings is test_settings

    def test_has_start_method(self):
        sig = inspect.signature(TaskRunner.start)
        params = list(sig.parameters)
        assert "task_id" in params
        assert "message" in params

    def test_has_cancel_method(self):
        sig = inspect.signature(TaskRunner.cancel)
        params = list(sig.parameters)
        assert "task_id" in params

    def test_has_is_running_method(self):
        assert hasattr(TaskRunner, "is_running")

    def test_no_active_runs_after_init(self, test_settings):
        runner = TaskRunner(test_settings)
        assert runner._active_runs == {}


async def _wait_for_runner(runner: TaskRunner, task_id: str) -> None:
    for _ in range(50):
        if not runner.is_running(task_id):
            return
        await asyncio.sleep(0.01)
    raise AssertionError("runner did not finish")


class _FakeStreamingAgent:
    def __init__(self, chunks: list[Any]) -> None:
        self._chunks = chunks

    async def astream(self, *args: Any, **kwargs: Any) -> AsyncIterator[Any]:
        for chunk in self._chunks:
            yield chunk


async def _wait_for_memory_tasks(runner: TaskRunner) -> None:
    for _ in range(50):
        if not runner._memory_tasks:
            return
        await asyncio.sleep(0.01)
    raise AssertionError("memory tasks did not finish")

def _event_record(
    *,
    task_id: str,
    run_id: str | None,
    event_type: str,
    message: str,
    payload: dict[str, Any] | None = None,
    seq: int = 0,
    level: Literal["info", "success", "warning", "error"] | None = "info",
) -> EventRecord:
    return EventRecord(
        id=f"{event_type}-{seq}",
        session_id=task_id,
        seq=seq,
        type=event_type,
        message=message,
        created_at="2026-05-21T00:00:00+00:00",
        payload=payload or {},
        run_id=run_id,
        level=level,
    )


class TestTaskRunnerStreamState:
    @pytest.mark.asyncio
    async def test_start_uses_only_root_values_snapshot_for_latest_state(
        self, test_settings, monkeypatch
    ):
        chunks: list[Any] = [
            {
                "type": "values",
                "ns": [],
                "data": {
                    "scope": "root",
                    "messages": [AIMessage(content="root final answer")],
                },
            },
            {
                "type": "values",
                "ns": ("researcher", "model"),
                "data": {
                    "scope": "subgraph",
                    "messages": [AIMessage(content="subgraph intermediate answer")],
                },
            },
        ]
        runner = TaskRunner(test_settings)

        monkeypatch.setattr(
            "app.runner.core.build_agent",
            lambda *args, **kwargs: _FakeStreamingAgent(chunks),
        )

        records, latest_state = await runner.start("task-1", "hello", run_id="run-1")
        snapshots = [record for record in records if record.type == "values_snapshot"]

        assert latest_state["scope"] == "root"
        assert [record.payload["is_subgraph"] for record in snapshots] == [False, True]

    @pytest.mark.asyncio
    async def test_start_scopes_streamed_events_to_current_run(
        self, test_settings, monkeypatch
    ):
        async def fake_stream_agent(agent, messages, config):
            del agent, messages, config
            yield {"type": "state_update", "data": {"node": "model", "is_subgraph": False}}
            yield {
                "type": "message_chunk",
                "data": {"content": "partial answer", "is_subgraph": False},
            }
            yield {
                "type": "values_snapshot",
                "data": {"messages": [AIMessage(content="done")], "is_subgraph": False},
            }

        monkeypatch.setattr("app.runner.core.build_agent", lambda *args, **kwargs: object())
        monkeypatch.setattr("app.runner.core.stream_agent", fake_stream_agent)

        runner = TaskRunner(test_settings)
        records, latest_state = await runner.start("task-1", "hello", run_id="run-1")

        assert [record.type for record in records] == [
            "status_update",
            "assistant_answer_delta",
            "values_snapshot",
        ]
        assert {record.run_id for record in records} == {"run-1"}
        assert records[0].payload["live"]["display_text"] == "AI正在思考..."
        assert records[1].payload["content"] == "partial answer"
        assert latest_state["messages"] == [AIMessage(content="done")]

    @pytest.mark.asyncio
    async def test_start_injects_resource_manifest_system_message(
        self, test_settings, monkeypatch
    ):
        task_id = "task-1"
        upload_dir = test_settings.workspace_root / task_id / "uploads"
        upload_dir.mkdir(parents=True)
        (upload_dir / "notes.txt").write_text("alpha body", encoding="utf-8")
        captured: dict[str, Any] = {}

        async def fake_stream_agent(agent, messages, config):
            captured["messages"] = messages
            yield {"type": "values_snapshot", "data": {"messages": [AIMessage(content="done")]}}

        def fake_build_agent(*args, **kwargs):
            captured["tools"] = kwargs["tools"]
            captured["system_prompt"] = kwargs["system_prompt"]
            return object()

        monkeypatch.setattr("app.runner.core.build_agent", fake_build_agent)
        monkeypatch.setattr("app.runner.core.stream_agent", fake_stream_agent)

        storage = InMemoryTaskStorage(test_settings.workspace_root)
        runner = TaskRunner(test_settings, storage=storage)
        await runner.start(task_id, "summarize uploads", run_id="run-1")

        assert "上传文件属于任务资源" in captured["system_prompt"]
        assert {tool.name for tool in captured["tools"]} >= {
            "list_uploaded_resources",
            "inspect_resource",
            "read_resource_text",
            "read_resource_table",
            "create_word_document",
        }
        assert "不要调用 bash、shell、python、execute" in captured["system_prompt"]
        system_messages = [
            message for message in captured["messages"] if isinstance(message, SystemMessage)
        ]
        manifest_text = "\n".join(str(message.content) for message in system_messages)
        assert "notes.txt" in manifest_text
        assert "alpha body" not in manifest_text


class TestTaskRunnerMemory:
    @pytest.mark.asyncio
    async def test_memory_recall_runs_off_event_loop_thread(self, test_settings, monkeypatch):
        event_loop_thread_id = threading.get_ident()
        captured_messages = []

        class ThreadCapturingMemoryService:
            def __init__(self) -> None:
                self.thread_id: int | None = None

            def recall_context(self, user_message: str, *, limit: int = 3) -> str | None:
                self.thread_id = threading.get_ident()
                return "历史偏好：先确认边界。"

            def remember_completed_run(
                self,
                *,
                task_id: str,
                run_id: str,
                user_goal: str,
                final_answer: str,
            ) -> None:
                return None

        async def fake_stream_agent(agent, messages, config):
            captured_messages.extend(messages)
            yield {"type": "values_snapshot", "data": {"messages": [AIMessage(content="done")]}}

        monkeypatch.setattr("app.runner.core.build_agent", lambda *args, **kwargs: object())
        monkeypatch.setattr("app.runner.core.stream_agent", fake_stream_agent)

        memory_service = ThreadCapturingMemoryService()
        runner = TaskRunner(test_settings, memory_service=memory_service)

        await runner.start("task-1", "hello", run_id="run-1")

        assert memory_service.thread_id is not None
        assert memory_service.thread_id != event_loop_thread_id
        assert any(
            isinstance(message, SystemMessage) and "先确认边界" in str(message.content)
            for message in captured_messages
        )

    @pytest.mark.asyncio
    async def test_memory_recall_failure_is_ignored(self, test_settings, monkeypatch):
        captured_messages = []

        class FailingRecallMemoryService:
            def recall_context(self, user_message: str, *, limit: int = 3) -> str | None:
                raise MemoryServiceError("Embedding 服务不可用")

            def remember_completed_run(
                self,
                *,
                task_id: str,
                run_id: str,
                user_goal: str,
                final_answer: str,
            ) -> None:
                return None

        async def fake_stream_agent(agent, messages, config):
            captured_messages.extend(messages)
            yield {"type": "values_snapshot", "data": {"messages": [AIMessage(content="done")]}}

        monkeypatch.setattr("app.runner.core.build_agent", lambda *args, **kwargs: object())
        monkeypatch.setattr("app.runner.core.stream_agent", fake_stream_agent)

        runner = TaskRunner(test_settings, memory_service=FailingRecallMemoryService())

        _, state = await runner.start("task-1", "hello", run_id="run-1")

        assert state["messages"] == [AIMessage(content="done")]
        assert all(not isinstance(message, SystemMessage) for message in captured_messages)


class TestTaskRunnerTerminalEvents:
    @pytest.mark.asyncio
    async def test_background_run_rebinds_streamed_events_to_current_run(
        self, test_settings, monkeypatch
    ):
        storage = InMemoryTaskStorage(test_settings.task_root)
        runner = TaskRunner(test_settings, storage)
        state = storage.create_task(message=None, model="deepseek-v4-flash")
        run_result = storage.start_run(
            state.task_id,
            message="hello",
            model="deepseek-v4-flash",
            expected_statuses={"idle"},
        )
        assert run_result is not None
        _, run_id = run_result

        async def fake_start(task_id: str, message: str, *, model: str | None, run_id: str, on_event=None):
            del message, model
            assert on_event is not None
            on_event(
                _event_record(
                    task_id=task_id,
                    run_id="stale-run",
                    event_type="status_update",
                    message="State update: model",
                    payload={"live": {"display_text": "AI正在思考"}},
                    seq=0,
                )
            )
            on_event(
                _event_record(
                    task_id=task_id,
                    run_id=None,
                    event_type="assistant_answer_delta",
                    message="partial answer",
                    payload={"content": "partial answer"},
                    seq=1,
                )
            )
            return [], {"messages": [AIMessage(content="done")]}

        monkeypatch.setattr(runner, "start", fake_start)

        runner.start_background(state.task_id, "hello", model="deepseek-v4-flash", run_id=run_id)
        await _wait_for_runner(runner, state.task_id)

        scoped_events = [
            event
            for event in storage.read_events(state.task_id)
            if event.type
            in {
                "status_update",
                "assistant_answer_delta",
                "task_completed",
                "final_answer",
            }
        ]

        assert [event.type for event in scoped_events] == [
            "status_update",
            "assistant_answer_delta",
            "task_completed",
            "final_answer",
        ]
        assert {event.run_id for event in scoped_events} == {run_id}

    @pytest.mark.asyncio
    async def test_successful_background_run_writes_task_completed_event(
        self, test_settings, monkeypatch
    ):
        storage = InMemoryTaskStorage(test_settings.task_root)
        runner = TaskRunner(test_settings, storage)
        state = storage.create_task(message=None, model="deepseek-v4-flash")
        run_result = storage.start_run(
            state.task_id,
            message="hello",
            model="deepseek-v4-flash",
            expected_statuses={"idle"},
        )
        assert run_result is not None
        _, run_id = run_result

        async def fake_start(*args, **kwargs):
            return [], {"messages": [AIMessage(content="done")]}

        monkeypatch.setattr(runner, "start", fake_start)

        runner.start_background(state.task_id, "hello", model="deepseek-v4-flash", run_id=run_id)
        await _wait_for_runner(runner, state.task_id)

        events = storage.read_events(state.task_id)
        completed = [event for event in events if event.type == "task_completed"]
        final_answers = [event for event in events if event.type == "final_answer"]

        assert len(completed) == 1
        assert completed[0].run_id == run_id
        assert completed[0].level == "success"
        assert completed[0].payload["live"]["display_text"] == "任务已完成"
        assert completed[0].payload["live"]["stage"] == "completed"
        assert len(final_answers) == 1
        assert final_answers[0].run_id == run_id
        assert final_answers[0].payload["content"] == "done"
        assert final_answers[0].payload["live"]["kind"] == "answer_status"
        assert final_answers[0].payload["live"]["display_text"] == "回答已完成"

    @pytest.mark.asyncio
    async def test_background_run_clarifies_missing_upload_as_assistant_message(
        self, test_settings, monkeypatch
    ):
        storage = InMemoryTaskStorage(test_settings.task_root)
        runner = TaskRunner(test_settings, storage)
        state = storage.create_task(message=None, model="deepseek-v4-flash")
        user_message = "请总结内容并生成 Word"
        run_result = storage.start_run(
            state.task_id,
            message=user_message,
            model="deepseek-v4-flash",
            expected_statuses={"idle"},
        )
        assert run_result is not None
        _, run_id = run_result

        async def fail_if_agent_starts(*args, **kwargs):
            raise AssertionError("missing-source clarification should not start the agent")

        monkeypatch.setattr(runner, "start", fail_if_agent_starts)

        runner.start_background(
            state.task_id,
            user_message,
            model="deepseek-v4-flash",
            run_id=run_id,
        )
        await _wait_for_runner(runner, state.task_id)

        task_state = storage.get_task(state.task_id)
        assistant_messages = [message for message in task_state.messages if message.role == "assistant"]
        needs_input_events = [event for event in task_state.events if event.type == "needs_input"]
        final_answers = [event for event in task_state.events if event.type == "final_answer"]

        assert task_state.status == "complete"
        assert task_state.needs_input is None
        assert task_state.runs[-1].status == "complete"
        assert task_state.runs[-1].needs_input is None
        assert needs_input_events == []
        assert len(assistant_messages) == 1
        assert "你是不是忘记上传文件了" in assistant_messages[0].content
        assert "继续帮你生成 Word" in assistant_messages[0].content
        assert len(final_answers) == 1
        assert final_answers[0].level == "success"
        assert final_answers[0].payload["content"] == assistant_messages[0].content

    @pytest.mark.asyncio
    async def test_background_run_requires_requested_deliverable_artifact_before_complete(
        self, test_settings, monkeypatch
    ):
        storage = InMemoryTaskStorage(test_settings.task_root)
        runner = TaskRunner(test_settings, storage)
        state = storage.create_task(message=None, model="deepseek-v4-flash")
        user_message = (
            "请根据以下项目材料生成一份 Word 文档并交付给我：\n"
            "项目A在第一阶段完成需求调研、接口梳理、风险识别和交付计划确认，需要形成正式文档。"
        )
        run_result = storage.start_run(
            state.task_id,
            message=user_message,
            model="deepseek-v4-flash",
            expected_statuses={"idle"},
        )
        assert run_result is not None
        _, run_id = run_result

        async def fake_start(*args, **kwargs):
            return [], {"messages": [AIMessage(content="已完成分析。")]}

        monkeypatch.setattr(runner, "start", fake_start)

        runner.start_background(
            state.task_id,
            user_message,
            model="deepseek-v4-flash",
            run_id=run_id,
        )
        await _wait_for_runner(runner, state.task_id)

        task_state = storage.get_task(state.task_id)
        needs_input_events = [event for event in task_state.events if event.type == "needs_input"]
        completed = [event for event in task_state.events if event.type == "task_completed"]
        final_answers = [event for event in task_state.events if event.type == "final_answer"]

        assert task_state.status == "needs_input"
        assert completed == []
        assert final_answers == []
        assert len(needs_input_events) == 1
        assert needs_input_events[0].run_id == run_id
        assert "文件未生成或未登记为产物" in needs_input_events[0].message
        assert task_state.needs_input is not None
        assert task_state.needs_input["reason"] == "deliverable_artifact_missing"
        assert task_state.runs[-1].status == "needs_input"

    @pytest.mark.parametrize(
        ("request_phrase", "artifact_name", "claimed_name"),
        [
            ("生成一份 Word 文档", "actual-summary.docx", "model-summary.docx"),
            ("生成一份 PPT 幻灯片", "actual-slides.pptx", "model-slides.pptx"),
            ("生成一份 Excel 表格", "actual-workbook.xlsx", "model-workbook.xlsx"),
            ("生成一份 Excel 表格", "actual-macro-workbook.xlsm", "model-workbook.xlsx"),
            ("生成一份报告", "actual-report.html", "model-report.html"),
            ("生成一份报告", "actual-report.md", "model-report.pdf"),
            ("生成一份报告", "actual-report.pdf", "model-report.html"),
        ],
    )
    @pytest.mark.asyncio
    async def test_background_run_accepts_any_artifact_matching_requested_deliverable_type(
        self,
        test_settings,
        monkeypatch,
        request_phrase: str,
        artifact_name: str,
        claimed_name: str,
    ):
        storage = InMemoryTaskStorage(test_settings.task_root)
        runner = TaskRunner(test_settings, storage)
        state = storage.create_task(message=None, model="deepseek-v4-flash")
        user_message = (
            f"请根据以下材料{request_phrase}并交付给我：\n"
            "项目资料包含范围边界、进度安排、风险负责人、验收方式和预算调整说明。"
        )
        run_result = storage.start_run(
            state.task_id,
            message=user_message,
            model="deepseek-v4-flash",
            expected_statuses={"idle"},
        )
        assert run_result is not None
        _, run_id = run_result
        storage.write_run_text(state.task_id, run_id, artifact_name, "placeholder")

        async def fake_start(*args, **kwargs):
            return [], {"messages": [AIMessage(content=f"已生成 {claimed_name}，请下载查看。")]}

        monkeypatch.setattr(runner, "start", fake_start)

        runner.start_background(
            state.task_id,
            user_message,
            model="deepseek-v4-flash",
            run_id=run_id,
        )
        await _wait_for_runner(runner, state.task_id)

        task_state = storage.get_task(state.task_id)
        needs_input_events = [event for event in task_state.events if event.type == "needs_input"]
        final_answers = [event for event in task_state.events if event.type == "final_answer"]

        assert task_state.status == "complete"
        assert task_state.needs_input is None
        assert task_state.runs[-1].status == "complete"
        assert artifact_name in task_state.runs[-1].artifact_names
        assert needs_input_events == []
        assert len(final_answers) == 1

    @pytest.mark.asyncio
    async def test_background_run_promotes_claimed_workspace_file_before_complete(
        self, test_settings, monkeypatch
    ):
        storage = InMemoryTaskStorage(test_settings.task_root)
        runner = TaskRunner(test_settings, storage)
        state = storage.create_task(message=None, model="deepseek-v4-flash")
        user_message = (
            "请根据以下材料输出简短总结，并把 Word 文档交付给我：\n"
            "本轮会议确认了实施范围、交付节点、风险负责人和后续验收安排。"
        )
        run_result = storage.start_run(
            state.task_id,
            message=user_message,
            model="deepseek-v4-flash",
            expected_statuses={"idle"},
        )
        assert run_result is not None
        _, run_id = run_result
        outputs_dir = test_settings.workspace_root / state.task_id / "outputs"
        outputs_dir.mkdir(parents=True, exist_ok=True)
        (outputs_dir / "brief.docx").write_bytes(b"docx bytes")

        async def fake_start(*args, **kwargs):
            return [], {"messages": [AIMessage(content="Word 文档已保存到 /root/brief.docx")]}

        monkeypatch.setattr(runner, "start", fake_start)

        runner.start_background(
            state.task_id,
            user_message,
            model="deepseek-v4-flash",
            run_id=run_id,
        )
        await _wait_for_runner(runner, state.task_id)

        task_state = storage.get_task(state.task_id)
        run = task_state.runs[-1]
        final_answers = [event for event in task_state.events if event.type == "final_answer"]

        assert task_state.status == "complete"
        assert "brief.docx" in run.artifact_names
        assert storage.resolve_run_artifact(state.task_id, run_id, "brief.docx").read_bytes() == b"docx bytes"
        assert len(final_answers) == 1

    @pytest.mark.asyncio
    async def test_background_run_accepts_markdown_linked_claimed_artifact(
        self, test_settings, monkeypatch
    ):
        storage = InMemoryTaskStorage(test_settings.task_root)
        runner = TaskRunner(test_settings, storage)
        state = storage.create_task(message=None, model="deepseek-v4-flash")
        run_result = storage.start_run(
            state.task_id,
            message="请总结一下内容，然后把总结的内容生成一个 Word 给我",
            model="deepseek-v4-flash",
            expected_statuses={"idle"},
        )
        assert run_result is not None
        _, run_id = run_result
        storage.write_run_text(state.task_id, run_id, "技术参数总结.docx", "placeholder")

        async def fake_start(*args, **kwargs):
            return [], {
                "messages": [
                    AIMessage(
                        content=(
                            "已生成 **[技术参数总结.docx]"
                            f"(/api/tasks/{state.task_id}/runs/{run_id}/artifacts/技术参数总结.docx)**"
                        )
                    )
                ]
            }

        monkeypatch.setattr(runner, "start", fake_start)

        runner.start_background(
            state.task_id,
            "请总结一下内容，然后把总结的内容生成一个 Word 给我",
            model="deepseek-v4-flash",
            run_id=run_id,
        )
        await _wait_for_runner(runner, state.task_id)

        task_state = storage.get_task(state.task_id)
        needs_input_events = [event for event in task_state.events if event.type == "needs_input"]
        final_answers = [event for event in task_state.events if event.type == "final_answer"]

        assert task_state.status == "complete"
        assert needs_input_events == []
        assert len(final_answers) == 1

    @pytest.mark.asyncio
    async def test_failed_background_run_writes_task_failed_event(
        self, test_settings, monkeypatch
    ):
        storage = InMemoryTaskStorage(test_settings.task_root)
        runner = TaskRunner(test_settings, storage)
        state = storage.create_task(message=None, model="deepseek-v4-flash")
        run_result = storage.start_run(
            state.task_id,
            message="hello",
            model="deepseek-v4-flash",
            expected_statuses={"idle"},
        )
        assert run_result is not None
        _, run_id = run_result

        async def fake_start(*args, **kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(runner, "start", fake_start)

        runner.start_background(state.task_id, "hello", model="deepseek-v4-flash", run_id=run_id)
        await _wait_for_runner(runner, state.task_id)

        failed = [event for event in storage.read_events(state.task_id) if event.type == "task_failed"]

        assert len(failed) == 1
        assert failed[0].run_id == run_id
        assert failed[0].payload["error"] == "boom"
        assert failed[0].payload["live"]["stage"] == "failed"
        assert failed[0].payload["live"]["display_text"] == "任务失败"
        assert storage.get_task(state.task_id).status == "failed"

    @pytest.mark.asyncio
    async def test_memory_write_failure_keeps_successful_run_complete(
        self, test_settings, monkeypatch
    ):
        storage = InMemoryTaskStorage(test_settings.task_root)

        class FailingMemoryService:
            def __init__(self) -> None:
                self.called = threading.Event()

            def recall_context(self, user_message: str, *, limit: int = 3) -> str | None:
                return None

            def remember_completed_run(
                self,
                *,
                task_id: str,
                run_id: str,
                user_goal: str,
                final_answer: str,
            ) -> None:
                self.called.set()
                raise MemoryServiceError("写入 Qdrant 记忆失败")

        memory_service = FailingMemoryService()
        runner = TaskRunner(test_settings, storage, memory_service=memory_service)
        state = storage.create_task(message=None, model="deepseek-v4-flash")
        run_result = storage.start_run(
            state.task_id,
            message="hello",
            model="deepseek-v4-flash",
            expected_statuses={"idle"},
        )
        assert run_result is not None
        _, run_id = run_result

        async def fake_start(*args, **kwargs):
            return [], {"messages": [AIMessage(content="done")]}

        monkeypatch.setattr(runner, "start", fake_start)

        runner.start_background(state.task_id, "hello", model="deepseek-v4-flash", run_id=run_id)
        await _wait_for_runner(runner, state.task_id)
        assert await asyncio.to_thread(memory_service.called.wait, 1)
        await _wait_for_memory_tasks(runner)

        events = storage.read_events(state.task_id)
        failed = [event for event in events if event.type == "task_failed"]
        completed = [event for event in events if event.type == "task_completed"]

        assert failed == []
        assert len(completed) == 1
        assert completed[0].run_id == run_id
        assert storage.get_task(state.task_id).status == "complete"

    @pytest.mark.asyncio
    async def test_memory_write_does_not_block_terminal_status(self, test_settings, monkeypatch):
        storage = InMemoryTaskStorage(test_settings.task_root)

        class BlockingMemoryService:
            def __init__(self) -> None:
                self.started = threading.Event()
                self.release = threading.Event()

            def recall_context(self, user_message: str, *, limit: int = 3) -> str | None:
                return None

            def remember_completed_run(
                self,
                *,
                task_id: str,
                run_id: str,
                user_goal: str,
                final_answer: str,
            ) -> None:
                self.started.set()
                self.release.wait(timeout=2)

        memory_service = BlockingMemoryService()
        runner = TaskRunner(test_settings, storage, memory_service=memory_service)
        state = storage.create_task(message=None, model="deepseek-v4-flash")
        run_result = storage.start_run(
            state.task_id,
            message="hello",
            model="deepseek-v4-flash",
            expected_statuses={"idle"},
        )
        assert run_result is not None
        _, run_id = run_result

        async def fake_start(*args, **kwargs):
            return [], {"messages": [AIMessage(content="done")]}

        monkeypatch.setattr(runner, "start", fake_start)

        runner.start_background(state.task_id, "hello", model="deepseek-v4-flash", run_id=run_id)
        await _wait_for_runner(runner, state.task_id)

        assert storage.get_task(state.task_id).status == "complete"
        assert not runner.is_running(state.task_id)
        assert await asyncio.to_thread(memory_service.started.wait, 1)

        memory_service.release.set()
        await _wait_for_memory_tasks(runner)

    @pytest.mark.asyncio
    async def test_cancelled_background_run_writes_run_scoped_cancel_event(
        self, test_settings, monkeypatch
    ):
        storage = InMemoryTaskStorage(test_settings.task_root)
        runner = TaskRunner(test_settings, storage)
        state = storage.create_task(message=None, model="deepseek-v4-flash")
        run_result = storage.start_run(
            state.task_id,
            message="hello",
            model="deepseek-v4-flash",
            expected_statuses={"idle"},
        )
        assert run_result is not None
        _, run_id = run_result

        async def fake_start(*args, **kwargs):
            await asyncio.sleep(60)
            return [], {}

        monkeypatch.setattr(runner, "start", fake_start)

        runner.start_background(state.task_id, "hello", model="deepseek-v4-flash", run_id=run_id)
        await asyncio.sleep(0)
        await runner.cancel(state.task_id)

        cancelled = [
            event for event in storage.read_events(state.task_id) if event.type == "task_cancelled"
        ]

        assert len(cancelled) == 1
        assert cancelled[0].run_id == run_id
        assert cancelled[0].payload["live"]["display_text"] == "任务已取消"
        assert cancelled[0].payload["live"]["result_status"] == "cancelled"
        assert storage.get_task(state.task_id).status == "cancelled"
