from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

import app.deep_agent_runtime as deep_agent_runtime
from app.orchestrator import DeepAgentOrchestrator
from app.permissions import PermissionPolicy
from app.runtime import CancellationController
from app.schemas import TaskStatus
from app.storage import TaskStorage
from app.tools import AuditedWorkspaceTools


def make_running_task(tmp_path: Path) -> tuple[TaskStorage, str, str]:
    storage = TaskStorage(tmp_path / "tasks")
    state = storage.create_task(None, "deepseek-reasoner")
    started = storage.start_run(
        state.task_id,
        message="检查上传文件",
        model="deepseek-reasoner",
        expected_statuses=cast(set[TaskStatus], {"idle"}),
    )
    assert started is not None
    return storage, state.task_id, started[1]


def test_deep_agent_mock_factory_gets_audited_file_tools_without_raw_filesystem(
    tmp_path: Path,
) -> None:
    storage, task_id, run_id = make_running_task(tmp_path)
    task_workspace = storage.task_dir(task_id)
    upload = task_workspace / "uploads" / "source.md"
    upload.write_text("# Source\nhello", encoding="utf-8")

    def fake_factory(
        *,
        model: str,
        tools: list[Any],
        system_prompt: str,
        subagents: list[dict[str, Any]],
        backend: Any,
    ) -> Any:
        assert model == "deepseek-reasoner"
        assert "DeepAgent" in system_prompt
        assert subagents[0]["name"] == "file-record-agent"
        assert backend.audited is True
        assert backend.virtual_mode is True
        assert isinstance(backend, deep_agent_runtime.AuditedDeepAgentBackend)
        tool_map = {tool.__name__: tool for tool in tools}
        assert set(tool_map) == {"list_dir", "read_file", "write_file"}
        assert all(not hasattr(tool, "__self__") for tool in tools)

        def fake_agent(payload: dict[str, Any]) -> dict[str, str]:
            assert payload["messages"][0]["content"] == "读取并写入文件"
            names = tool_map["list_dir"]("uploads")
            text = tool_map["read_file"]("uploads/source.md")
            write_result = tool_map["write_file"]("outputs/notes.md", "done")
            assert write_result == {
                "relative_path": "outputs/notes.md",
                "bytes": 4,
            }
            return {"content": f"{names[0]}:{text}:{write_result['relative_path']}"}

        return fake_agent

    result = DeepAgentOrchestrator(
        storage=storage,
        task_id=task_id,
        run_id=run_id,
        model="deepseek-reasoner",
        controller=CancellationController(),
        uploads=[upload],
        agent_factory=fake_factory,
    ).run("读取并写入文件")

    agent_workspace = task_workspace / "agent_workspace" / "runs" / run_id
    audit_payloads = [
        event.payload for event in storage.read_events(task_id) if event.type == "file_tool_audit"
    ]
    events = storage.read_events(task_id)
    reasoning_payloads = [
        event.payload for event in events if event.type == "reasoning_trace"
    ]
    audit_event_ids = {event.id for event in events if event.type == "file_tool_audit"}
    serialized_payloads = json.dumps(audit_payloads, ensure_ascii=False)
    serialized_reasoning = json.dumps(reasoning_payloads, ensure_ascii=False)

    assert result.status == "complete"
    assert result.output_text.startswith("source.md:# Source")
    assert (agent_workspace / "outputs" / "notes.md").read_text(encoding="utf-8") == "done"
    assert (task_workspace / "artifacts" / "runs" / run_id / "deep-agent-notes.md").read_text(
        encoding="utf-8"
    ) == "done"
    assert result.metadata["workspace_root"] == f"agent_workspace/runs/{run_id}"
    assert result.metadata["promoted_artifacts"] == ["deep-agent-notes.md"]
    assert [payload["tool"] for payload in audit_payloads] == [
        "list_dir",
        "read_file",
        "write_file",
    ]
    assert all(
        {
            "tool",
            "operation",
            "requested_path",
            "relative_path",
            "status",
            "reason",
            "bytes",
            "partial",
            "op",
            "virtual_path",
            "resolved_workspace_path",
            "tool_name",
            "timestamp",
            "source",
            "sha256",
            "promoted_artifact_id",
            "run_id",
        }.issubset(payload)
        for payload in audit_payloads
    )
    assert audit_payloads[1]["requested_path"] == "uploads/source.md"
    assert audit_payloads[1]["relative_path"] == "uploads/source.md"
    assert audit_payloads[1]["source"] == "upload_snapshot"
    assert audit_payloads[2]["source"] == "output"
    assert {payload["status"] for payload in audit_payloads} == {"success"}
    assert str(task_workspace) not in serialized_payloads
    assert [payload["phase"] for payload in reasoning_payloads] == [
        "plan",
        "observe",
        "observe",
        "observe",
        "final_summary",
    ]
    assert all(
        payload.get("source_event_id") in audit_event_ids
        for payload in reasoning_payloads
        if payload["phase"] == "observe"
    )
    assert "uploads/source.md" in serialized_reasoning
    assert "outputs/notes.md" in serialized_reasoning
    assert "# Source" not in serialized_reasoning
    assert "hello" not in serialized_reasoning
    assert "读取并写入文件" not in serialized_reasoning
    assert str(task_workspace) not in serialized_reasoning


def test_deep_agent_runtime_missing_dependency_is_optional(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(deep_agent_runtime, "_DEFAULT_AGENT_FACTORY", None)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    runtime = deep_agent_runtime.DeepAgentRuntime(
        AuditedWorkspaceTools(workspace, PermissionPolicy(workspace))
    )

    assert not runtime.is_available
    with pytest.raises(deep_agent_runtime.DeepAgentUnavailableError, match="未安装"):
        runtime.run(
            deep_agent_runtime.DeepAgentRunRequest(
                task_id="task",
                run_id="run-20260428-test",
                message="hello",
                model="deepseek-reasoner",
            )
        )


def test_audited_deep_agent_backend_protocol_methods_are_audited(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "uploads").mkdir(parents=True)
    (workspace / "records").mkdir()
    (workspace / "outputs").mkdir()
    (workspace / "uploads" / "source.md").write_text("hello world\nsecond", encoding="utf-8")
    records: list[dict[str, Any]] = []
    backend = deep_agent_runtime.AuditedDeepAgentBackend(
        AuditedWorkspaceTools(
            workspace,
            PermissionPolicy(workspace),
            audit_sink=records.append,
        )
    )

    listed = backend.ls("/")
    read = backend.read("/uploads/source.md")
    written = backend.write("/outputs/new.md", "draft")
    edited = backend.edit("/outputs/new.md", "draft", "final")
    globbed = backend.glob("*.md", "/outputs")
    grepped = backend.grep("hello", "/uploads", "*.md")
    denied = backend.write("/uploads/mutate.md", "bad")

    assert listed.error is None
    assert {entry["path"] for entry in listed.entries or []} >= {
        "/uploads",
        "/records",
        "/outputs",
    }
    assert read.error is None
    assert read.file_data is not None
    assert read.file_data["content"] == "hello world\nsecond"
    assert written.error is None
    assert written.path == "/outputs/new.md"
    assert edited.error is None
    assert edited.occurrences == 1
    assert (workspace / "outputs" / "new.md").read_text(encoding="utf-8") == "final"
    assert globbed.error is None
    assert [match["path"] for match in globbed.matches or []] == ["/outputs/new.md"]
    assert grepped.error is None
    assert grepped.matches and grepped.matches[0]["path"] == "/uploads/source.md"
    assert denied.error and "只能写入" in denied.error
    assert {record["tool"] for record in records} >= {"list_dir", "read_file", "write_file"}
    assert any(record["tool"] == "glob" and record["op"] == "glob" for record in records)
    assert any(record["tool"] == "grep" and record["op"] == "grep" for record in records)
    assert all(str(workspace) not in json.dumps(record, ensure_ascii=False) for record in records)


@pytest.mark.parametrize(
    ("virtual_path", "stored_path"),
    [
        ("/large_tool_results/result-1.md", "records/deepagents/large_tool_results/result-1.md"),
        (
            "/conversation_history/summary.md",
            "records/deepagents/conversation_history/summary.md",
        ),
    ],
)
def test_audited_deep_agent_backend_maps_internal_prefixes_to_records(
    tmp_path: Path, virtual_path: str, stored_path: str
) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "records").mkdir(parents=True)
    (workspace / "outputs").mkdir()
    records: list[dict[str, Any]] = []
    backend = deep_agent_runtime.AuditedDeepAgentBackend(
        AuditedWorkspaceTools(
            workspace,
            PermissionPolicy(workspace),
            audit_sink=records.append,
        )
    )

    written = backend.write(virtual_path, "internal")
    read = backend.read(virtual_path)

    assert written.error is None
    assert written.path == virtual_path
    assert read.error is None
    assert read.file_data is not None
    assert read.file_data["content"] == "internal"
    assert (workspace / stored_path).read_text(encoding="utf-8") == "internal"
    assert records[-2]["relative_path"] == stored_path
    assert records[-2]["source"] == "record"


def test_audited_file_tools_deny_traversal_with_redacted_audit(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    records: list[dict[str, Any]] = []
    tools = AuditedWorkspaceTools(
        workspace,
        PermissionPolicy(workspace),
        audit_sink=records.append,
    )

    with pytest.raises(PermissionError, match="任务工作区"):
        tools.read_file("../secret.md")

    assert records[-1]["status"] == "denied"
    assert records[-1]["requested_path"] == "../secret.md"
    assert records[-1]["relative_path"] is None
    assert str(tmp_path) not in json.dumps(records, ensure_ascii=False)


@pytest.mark.parametrize(
    "raw_path",
    [
        r"D:\AgentProject\secret\file.md",
        r"\\server\share\private\file.md",
    ],
)
def test_audited_file_tools_redact_windows_absolute_paths(
    tmp_path: Path, raw_path: str
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    records: list[dict[str, Any]] = []
    tools = AuditedWorkspaceTools(
        workspace,
        PermissionPolicy(workspace),
        audit_sink=records.append,
    )

    with pytest.raises(PermissionError, match="任务工作区"):
        tools.read_file(raw_path)

    serialized = json.dumps(records, ensure_ascii=False)
    assert records[-1]["requested_path"] == "<outside-workspace>/file.md"
    assert records[-1]["virtual_path"] == "<outside-workspace>/file.md"
    assert "AgentProject" not in serialized
    assert "server" not in serialized
    assert str(tmp_path) not in serialized


def test_audited_file_tools_cancel_before_access_records_cancelled(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "uploads").mkdir(parents=True)
    records: list[dict[str, Any]] = []
    controller = CancellationController()
    controller.cancel()
    tools = AuditedWorkspaceTools(
        workspace,
        PermissionPolicy(workspace),
        controller,
        records.append,
    )

    with pytest.raises(RuntimeError, match="取消"):
        tools.list_dir("uploads")

    assert records[-1]["status"] == "cancelled"
    assert records[-1]["requested_path"] == "uploads"
    assert records[-1]["relative_path"] is None
    assert records[-1]["partial"] is False


def test_audited_file_tools_deny_writes_outside_records_and_outputs(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "uploads").mkdir(parents=True)
    records: list[dict[str, Any]] = []
    tools = AuditedWorkspaceTools(
        workspace,
        PermissionPolicy(workspace),
        audit_sink=records.append,
    )

    with pytest.raises(PermissionError, match="只能写入"):
        tools.write_file("uploads/source.md", "mutate")

    assert records[-1]["status"] == "denied"
    assert records[-1]["relative_path"] == "uploads/source.md"
    assert not (workspace / "uploads" / "source.md").exists()


class CancelsAfterChecks(CancellationController):
    def __init__(self, limit: int) -> None:
        super().__init__()
        self.limit = limit
        self.checks = 0

    def raise_if_cancelled(self) -> None:
        self.checks += 1
        if self.checks >= self.limit:
            self.cancel()
        super().raise_if_cancelled()


def test_audited_file_tools_cancelled_partial_write_is_not_published(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    records: list[dict[str, Any]] = []
    tools = AuditedWorkspaceTools(
        workspace,
        PermissionPolicy(workspace),
        CancelsAfterChecks(limit=4),
        records.append,
        write_chunk_chars=2,
    )

    with pytest.raises(RuntimeError, match="取消"):
        tools.write_file("outputs/partial.md", "abcdef")

    output_dir = workspace / "outputs"
    assert not (output_dir / "partial.md").exists()
    assert list(output_dir.glob(".*.tmp")) == []
    assert records[-1]["status"] == "cancelled"
    assert records[-1]["relative_path"] == "outputs/partial.md"
    assert records[-1]["bytes"] == 2
    assert records[-1]["partial"] is True
