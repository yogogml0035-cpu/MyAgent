from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

import app.deep_agent_runtime as deep_agent_runtime
from app.agent_activity import (
    build_live_tool_call_metadata,
    build_live_tool_result_metadata,
)
from app.agent_profiles import (
    BID_MULTI_AGENT_PROFILE_ID,
    AgentProfile,
    AgentProfileValidationError,
    SubAgentSpec,
    compile_subagents_for_deepagents,
    get_agent_profile,
    validate_agent_profile,
)
from app.orchestrator import DeepAgentOrchestrator
from app.permissions import PermissionPolicy
from app.runtime import CancellationController
from app.schemas import TaskStatus
from app.storage import TaskStorage
from app.tools import AuditedWorkspaceTools


def make_running_task(tmp_path: Path) -> tuple[TaskStorage, str, str]:
    storage = TaskStorage(tmp_path / "sessions")
    state = storage.create_task(None, "deepseek-reasoner")
    started = storage.start_run(
        state.task_id,
        message="检查上传文件",
        model="deepseek-reasoner",
        expected_statuses=cast(set[TaskStatus], {"idle"}),
    )
    assert started is not None
    return storage, state.task_id, started[1]


def write_bid_upload_fixtures(task_workspace: Path) -> list[Path]:
    tender = task_workspace / "uploads" / "招标文件.md"
    bidder_a = task_workspace / "uploads" / "甲公司.md"
    bidder_b = task_workspace / "uploads" / "乙公司.md"
    bidder_c = task_workspace / "uploads" / "丙公司.md"
    tender.write_text("# 招标文件\n采购需求。", encoding="utf-8")
    bidder_a.write_text("# 甲公司\n投标人：甲公司\n报价 100 万元。", encoding="utf-8")
    bidder_b.write_text("# 乙公司\n投标人：乙公司\n报价 100 万元。", encoding="utf-8")
    bidder_c.write_text("# 丙公司\n投标人：丙公司\n报价 120 万元。", encoding="utf-8")
    return [tender, bidder_a, bidder_b, bidder_c]


def fake_tool_registry() -> dict[str, Any]:
    def list_dir(_relative_path: str = ".") -> list[str]:
        return []

    def read_file(_relative_path: str) -> str:
        return ""

    def write_file(_relative_path: str, _content: str) -> dict[str, Any]:
        return {}

    return {
        "list_dir": list_dir,
        "read_file": read_file,
        "write_file": write_file,
    }


def tool_names(tools: list[Any]) -> set[str]:
    return {tool.__name__ for tool in tools}


def test_agent_profile_registry_validates_static_bid_profile() -> None:
    profile = get_agent_profile(BID_MULTI_AGENT_PROFILE_ID)
    compiled = compile_subagents_for_deepagents(profile, fake_tool_registry())

    assert profile.strategy == "multi_agent"
    assert profile.planned_subagents == [
        "document-classification-agent",
        "requirement-matching-agent",
        "bidder-pair-comparison-agent",
        "evidence-normalization-agent",
        "report-writing-agent",
    ]
    assert [item["name"] for item in compiled] == profile.planned_subagents
    assert all(
        tool_names(item["tools"]) == {"list_dir", "read_file", "write_file"}
        for item in compiled
    )


def test_agent_profile_validation_rejects_unsafe_specs() -> None:
    base_subagent = SubAgentSpec(
        name="safe-agent",
        description="安全子 Agent",
        system_prompt="只使用授权工具。",
    )
    duplicate_profile = AgentProfile(
        id="unsafe-profile",
        label="Unsafe",
        strategy="multi_agent",
        reason_code="unsafe",
        system_prompt_fragment="unsafe",
        subagents=(base_subagent, base_subagent),
    )
    unsafe_tool_profile = AgentProfile(
        id="unsafe-tool-profile",
        label="Unsafe",
        strategy="single_agent",
        reason_code="unsafe",
        system_prompt_fragment="unsafe",
        subagents=(
            SubAgentSpec(
                name="unsafe-agent",
                description="尝试使用未授权工具",
                system_prompt="不要执行。",
                tool_aliases=("shell",),
            ),
        ),
    )
    unsafe_model_profile = AgentProfile(
        id="unsafe-model-profile",
        label="Unsafe",
        strategy="single_agent",
        reason_code="unsafe",
        system_prompt_fragment="unsafe",
        subagents=(
            SubAgentSpec(
                name="unsafe-model-agent",
                description="尝试覆盖模型",
                system_prompt="不要执行。",
                model="unknown-model",
            ),
        ),
        model_override_policy="allowlisted",
    )

    with pytest.raises(AgentProfileValidationError, match="重复"):
        validate_agent_profile(duplicate_profile)
    with pytest.raises(AgentProfileValidationError, match="未授权"):
        validate_agent_profile(unsafe_tool_profile)
    with pytest.raises(AgentProfileValidationError, match="未授权"):
        validate_agent_profile(unsafe_model_profile)


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
        assert tool_names(subagents[0]["tools"]) == set(tool_map)

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


def test_deep_agent_activity_warning_uses_safe_exception_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage, task_id, run_id = make_running_task(tmp_path)
    task_workspace = storage.task_dir(task_id)
    upload = task_workspace / "uploads" / "source.md"
    upload.write_text("# Source", encoding="utf-8")
    raw_error = (
        f"activity failed at {tmp_path}/private/customer.md with "
        "Authorization: Bearer AUTH_HEADER_CANARY_789 and SECRET_DOC_CANARY_123"
    )

    def fake_factory(**_kwargs: Any) -> Any:
        def fake_agent(_payload: dict[str, Any]) -> dict[str, str]:
            return {"content": "done"}

        return fake_agent

    def raise_activity_error(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise RuntimeError(raw_error)

    monkeypatch.setattr(
        "app.orchestrator.activity_payload_from_file_audit",
        raise_activity_error,
    )
    orchestrator = DeepAgentOrchestrator(
        storage=storage,
        task_id=task_id,
        run_id=run_id,
        model="deepseek-reasoner",
        controller=CancellationController(),
        uploads=[upload],
        agent_factory=fake_factory,
    )

    orchestrator._append_audit(
        {
            "tool": "read_file",
            "tool_name": "read_file",
            "operation": "read",
            "op": "read",
            "requested_path": "uploads/source.md",
            "virtual_path": "uploads/source.md",
            "relative_path": "uploads/source.md",
            "resolved_workspace_path": "uploads/source.md",
            "status": "success",
            "reason": "文件读取成功",
            "bytes": 8,
            "sha256": None,
            "partial": False,
            "source": "upload_snapshot",
            "promoted_artifact_id": None,
            "timestamp": None,
        }
    )

    warning_event = next(
        event for event in storage.read_events(task_id) if event.type == "deep_agent_activity_warning"
    )
    serialized_warning = json.dumps(warning_event.payload, ensure_ascii=False)
    assert warning_event.payload["error_type"] == "RuntimeError"
    assert "AUTH_HEADER_CANARY_789" not in serialized_warning
    assert "SECRET_DOC_CANARY_123" not in serialized_warning
    assert str(tmp_path) not in serialized_warning
    assert "<redacted-canary>" in serialized_warning
    assert "<absolute-path>/customer.md" in serialized_warning


def test_deep_agent_available_uploads_are_not_read_until_agent_chooses(
    tmp_path: Path,
) -> None:
    storage, task_id, run_id = make_running_task(tmp_path)
    task_workspace = storage.task_dir(task_id)
    upload = task_workspace / "uploads" / "source.md"
    upload.write_text("# Source\nsecret canary", encoding="utf-8")

    def fake_factory(
        *,
        model: str,
        tools: list[Any],
        system_prompt: str,
        subagents: list[dict[str, Any]],
        backend: Any,
    ) -> Any:
        assert model == "deepseek-reasoner"
        assert "是否列出、检索或读取" in system_prompt
        assert "任务需要时才读取" in subagents[0]["system_prompt"]
        assert isinstance(backend, deep_agent_runtime.AuditedDeepAgentBackend)
        tool_map = {tool.__name__: tool for tool in tools}
        assert tool_names(subagents[0]["tools"]) == set(tool_map)

        def fake_agent(_payload: dict[str, Any]) -> dict[str, str]:
            tool_map["write_file"]("outputs/notes.md", "did not inspect uploads")
            return {"content": "我没有读取上传文件。"}

        return fake_agent

    result = DeepAgentOrchestrator(
        storage=storage,
        task_id=task_id,
        run_id=run_id,
        model="deepseek-reasoner",
        controller=CancellationController(),
        uploads=[upload],
        agent_factory=fake_factory,
    ).run("根据需要决定是否读取文件")

    agent_workspace = task_workspace / "agent_workspace" / "runs" / run_id
    audit_payloads = [
        event.payload for event in storage.read_events(task_id) if event.type == "file_tool_audit"
    ]
    serialized_events = json.dumps(
        [event.payload for event in storage.read_events(task_id)],
        ensure_ascii=False,
    )

    assert result.output_text == "我没有读取上传文件。"
    assert (agent_workspace / "uploads" / "source.md").exists()
    assert [payload["operation"] for payload in audit_payloads] == ["write"]
    assert "secret canary" not in serialized_events
    assert str(task_workspace) not in serialized_events


def test_deep_agent_promotes_outputs_with_safe_unique_artifact_names(
    tmp_path: Path,
) -> None:
    storage, task_id, run_id = make_running_task(tmp_path)
    task_workspace = storage.task_dir(task_id)

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
        assert isinstance(backend, deep_agent_runtime.AuditedDeepAgentBackend)
        tool_map = {tool.__name__: tool for tool in tools}
        assert tool_names(subagents[0]["tools"]) == set(tool_map)

        def fake_agent(_payload: dict[str, Any]) -> dict[str, str]:
            tool_map["write_file"]("outputs/final summary.md", "space")
            tool_map["write_file"]("outputs/final#summary.md", "hash")
            tool_map["write_file"]("outputs/结果 报告.md", "cn")
            return {"content": "DeepAgent 已生成多个输出。"}

        return fake_agent

    result = DeepAgentOrchestrator(
        storage=storage,
        task_id=task_id,
        run_id=run_id,
        model="deepseek-reasoner",
        controller=CancellationController(),
        agent_factory=fake_factory,
    ).run("生成带有复杂文件名的输出")

    expected_artifacts = [
        "deep-agent-final_summary.md",
        "deep-agent-2-final_summary.md",
        "deep-agent-结果_报告.md",
    ]
    artifact_dir = task_workspace / "artifacts" / "runs" / run_id
    state = storage.get_task(task_id, include_events=False)
    run_record = next(run for run in state.runs if run.id == run_id)

    assert result.status == "complete"
    assert result.metadata["promoted_artifacts"] == expected_artifacts
    assert sorted(run_record.artifact_names) == sorted(expected_artifacts)
    assert (artifact_dir / "deep-agent-final_summary.md").read_text(encoding="utf-8") == "space"
    assert (artifact_dir / "deep-agent-2-final_summary.md").read_text(encoding="utf-8") == "hash"
    assert (artifact_dir / "deep-agent-结果_报告.md").read_text(encoding="utf-8") == "cn"


def test_deep_agent_promotes_valid_bid_outputs_to_canonical_artifacts(
    tmp_path: Path,
) -> None:
    storage, task_id, run_id = make_running_task(tmp_path)
    task_workspace = storage.task_dir(task_id)
    uploads = write_bid_upload_fixtures(task_workspace)

    def fake_factory(
        *,
        tools: list[Any],
        **_kwargs: Any,
    ) -> Any:
        tool_map = {tool.__name__: tool for tool in tools}

        def fake_agent(_payload: dict[str, Any]) -> dict[str, str]:
            evidence = [
                {
                    "category": "quotation_similarity",
                    "severity": "medium",
                    "title": "重复报价",
                    "description": "甲公司与乙公司存在重复报价数值。",
                    "bidders": ["甲公司", "乙公司"],
                    "pair": ["甲公司", "乙公司"],
                    "locations": [],
                    "requirement_reference": None,
                    "confidence": 0.72,
                    "source_agent": "bidder-pair-comparison-agent",
                    "rationale_summary": "报价清单出现重复数值。",
                },
                {
                    "category": "pair_comparison_coverage",
                    "severity": "low",
                    "title": "未发现可记录疑点",
                    "description": "未发现甲公司与丙公司的结构化疑点。",
                    "bidders": ["甲公司", "丙公司"],
                    "pair": ["甲公司", "丙公司"],
                    "locations": [],
                    "requirement_reference": None,
                    "confidence": 0.3,
                    "source_agent": "evidence-normalization-agent",
                    "rationale_summary": "已覆盖该投标人组合。",
                },
                {
                    "category": "pair_comparison_coverage",
                    "severity": "low",
                    "title": "未发现可记录疑点",
                    "description": "未发现乙公司与丙公司的结构化疑点。",
                    "bidders": ["乙公司", "丙公司"],
                    "pair": ["乙公司", "丙公司"],
                    "locations": [],
                    "requirement_reference": None,
                    "confidence": 0.3,
                    "source_agent": "evidence-normalization-agent",
                    "rationale_summary": "已覆盖该投标人组合。",
                },
            ]
            tool_map["write_file"]("outputs/report.html", "<html><body>报告</body></html>")
            tool_map["write_file"]("outputs/final-summary.md", "# 摘要\n已完成。")
            tool_map["write_file"]("outputs/evidence.json", json.dumps(evidence, ensure_ascii=False))
            tool_map["write_file"]("outputs/task-plan.md", "# 计划")
            tool_map["write_file"]("outputs/notes.md", "internal note")
            return {"content": "DeepAgent 已完成围串标分析。"}

        return fake_agent

    result = DeepAgentOrchestrator(
        storage=storage,
        task_id=task_id,
        run_id=run_id,
        model="deepseek-reasoner",
        controller=CancellationController(),
        uploads=uploads,
        agent_factory=fake_factory,
    ).run("帮我检查是否有串标围标嫌疑")

    artifact_dir = task_workspace / "artifacts" / "runs" / run_id
    state = storage.get_task(task_id, include_events=False)
    run_record = next(run for run in state.runs if run.id == run_id)

    assert set(result.metadata["promoted_artifacts"]) == {
        "report.html",
        "final-summary.md",
        "evidence.json",
        "task-plan.md",
        "deep-agent-notes.md",
    }
    assert "deep-agent-report.html" not in result.metadata["promoted_artifacts"]
    assert set(run_record.artifact_names) == set(result.metadata["promoted_artifacts"])
    assert (artifact_dir / "report.html").exists()
    assert (artifact_dir / "evidence.json").exists()


def test_deep_agent_bid_outputs_without_evidence_use_prefixed_artifacts(
    tmp_path: Path,
) -> None:
    storage, task_id, run_id = make_running_task(tmp_path)
    task_workspace = storage.task_dir(task_id)

    def fake_factory(*, tools: list[Any], **_kwargs: Any) -> Any:
        tool_map = {tool.__name__: tool for tool in tools}

        def fake_agent(_payload: dict[str, Any]) -> dict[str, str]:
            tool_map["write_file"]("outputs/report.html", "<html><body>报告</body></html>")
            tool_map["write_file"]("outputs/final-summary.md", "# 摘要\n缺少证据。")
            tool_map["write_file"]("outputs/task-plan.md", "# 计划")
            return {"content": "DeepAgent 已完成围串标分析。"}

        return fake_agent

    result = DeepAgentOrchestrator(
        storage=storage,
        task_id=task_id,
        run_id=run_id,
        model="deepseek-reasoner",
        controller=CancellationController(),
        agent_factory=fake_factory,
    ).run("帮我检查是否有串标围标嫌疑")

    artifact_dir = task_workspace / "artifacts" / "runs" / run_id

    assert set(result.metadata["promoted_artifacts"]) == {
        "deep-agent-report.html",
        "deep-agent-final-summary.md",
        "deep-agent-task-plan.md",
    }
    assert not (artifact_dir / "report.html").exists()
    assert not (artifact_dir / "final-summary.md").exists()
    assert not (artifact_dir / "task-plan.md").exists()
    assert (artifact_dir / "deep-agent-report.html").exists()


def test_deep_agent_bid_canonical_evidence_requires_all_uploaded_bidder_pairs(
    tmp_path: Path,
) -> None:
    storage, task_id, run_id = make_running_task(tmp_path)
    task_workspace = storage.task_dir(task_id)
    uploads = write_bid_upload_fixtures(task_workspace)

    def fake_factory(*, tools: list[Any], **_kwargs: Any) -> Any:
        tool_map = {tool.__name__: tool for tool in tools}

        def fake_agent(_payload: dict[str, Any]) -> dict[str, str]:
            evidence = [
                {
                    "category": "quotation_similarity",
                    "severity": "medium",
                    "title": "重复报价",
                    "description": "甲公司与乙公司存在重复报价数值。",
                    "bidders": ["甲公司", "乙公司"],
                    "pair": ["甲公司", "乙公司"],
                    "locations": [],
                    "requirement_reference": None,
                    "confidence": 0.72,
                    "source_agent": "bidder-pair-comparison-agent",
                    "rationale_summary": "报价清单出现重复数值。",
                }
            ]
            tool_map["write_file"]("outputs/report.html", "<html><body>报告</body></html>")
            tool_map["write_file"]("outputs/evidence.json", json.dumps(evidence, ensure_ascii=False))
            return {"content": "DeepAgent 已完成围串标分析。"}

        return fake_agent

    with pytest.raises(ValueError, match="缺少投标人组合覆盖记录"):
        DeepAgentOrchestrator(
            storage=storage,
            task_id=task_id,
            run_id=run_id,
            model="deepseek-reasoner",
            controller=CancellationController(),
            uploads=uploads,
            agent_factory=fake_factory,
        ).run("帮我检查是否有串标围标嫌疑")

    artifact_dir = task_workspace / "artifacts" / "runs" / run_id
    assert not (artifact_dir / "report.html").exists()
    assert not (artifact_dir / "evidence.json").exists()


def test_deep_agent_runtime_streams_with_required_options_and_activity_events(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    activity_events: list[dict[str, Any]] = []

    class StreamingAgent:
        def __init__(self) -> None:
            self.payload: dict[str, Any] | None = None
            self.kwargs: dict[str, Any] = {}

        def stream(self, payload: dict[str, Any], **kwargs: Any):
            self.payload = payload
            self.kwargs = kwargs
            yield ("updates", {"agent": {"status": "running"}})
            yield ("messages", ({"role": "assistant", "content": "最终答案"}, {}))

        def invoke(self, _payload: dict[str, Any], **_kwargs: Any) -> dict[str, str]:
            raise AssertionError("stream-capable agent should not use invoke")

    agent = StreamingAgent()

    def fake_factory(**_kwargs: Any) -> StreamingAgent:
        return agent

    runtime = deep_agent_runtime.DeepAgentRuntime(
        AuditedWorkspaceTools(workspace, PermissionPolicy(workspace)),
        agent_factory=fake_factory,
        activity_sink=activity_events.append,
    )

    result = runtime.run(
        deep_agent_runtime.DeepAgentRunRequest(
            task_id="task",
            run_id="run-20260428-stream",
            message="hello",
            model="deepseek-reasoner",
        )
    )

    assert result.output_text == "最终答案"
    assert result.metadata["execution_mode"] == "stream"
    assert agent.payload == {"messages": [{"role": "user", "content": "hello"}]}
    assert agent.kwargs["config"] == {
        "configurable": {"thread_id": "task:run-20260428-stream"}
    }
    assert agent.kwargs["subgraphs"] is True
    assert agent.kwargs["version"] == "v2"
    assert agent.kwargs["stream_mode"] == ["updates", "messages"]
    assert [event["status"] for event in activity_events] == [
        "started",
        "running",
        "running",
        "completed",
    ]
    assert activity_events[0]["live"]["stage"] == "analyzing_intent"
    answer_status_events = [
        event
        for event in activity_events
        if event.get("live", {}).get("kind") == "answer_status"
    ]
    assert [event["live"]["stage"] for event in answer_status_events] == [
        "generating_answer",
        "completed",
    ]
    assert all(event["schema_version"] == 1 for event in activity_events)
    assert all(event["source"] == "deepagents" for event in activity_events)


def test_deep_agent_runtime_activity_sanitizes_tool_args_results_and_paths(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    activity_events: list[dict[str, Any]] = []

    class StreamingAgent:
        def stream(self, _payload: dict[str, Any], **_kwargs: Any):
            yield (
                "messages",
                (
                    {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "name": "read_file",
                                "args": {
                                    "relative_path": "uploads/source.md",
                                    "path": "/mnt/d/private/customer/source.md",
                                    "content": "CUSTOMER_UPLOADED_BODY",
                                    "api_key": "sk-abcdefghijklmnop",
                                },
                            }
                        ],
                    },
                    {},
                ),
            )
            yield (
                "messages",
                (
                    {
                        "role": "tool",
                        "name": "read_file",
                        "content": (
                            "CUSTOMER_UPLOADED_BODY SECRET_DOC_CANARY_123 "
                            "Authorization: Bearer abcdefghijklmnop "
                            r"C:\Users\0325\secret.txt"
                        ),
                    },
                    {},
                ),
            )
            yield (
                "messages",
                (
                    {
                        "role": "tool",
                        "name": "read_file",
                        "content": {
                            "error": (
                                "CUSTOMER_UPLOADED_BODY SECRET_DOC_CANARY_123 "
                                "Authorization: Bearer abcdefghijklmnop"
                            ),
                            "path": "/mnt/d/private/customer/source.md",
                            "bytes": 77,
                        },
                    },
                    {},
                ),
            )
            yield ("messages", ({"role": "assistant", "content": "安全结论"}, {}))

    runtime = deep_agent_runtime.DeepAgentRuntime(
        AuditedWorkspaceTools(workspace, PermissionPolicy(workspace)),
        agent_factory=lambda **_kwargs: StreamingAgent(),
        activity_sink=activity_events.append,
    )

    result = runtime.run(
        deep_agent_runtime.DeepAgentRunRequest(
            task_id="task",
            run_id="run-20260428-sanitize",
            message="hello",
            model="deepseek-reasoner",
        )
    )
    serialized = json.dumps(activity_events, ensure_ascii=False)
    tool_started = next(
        event
        for event in activity_events
        if event["phase"] == "tool_use" and event["status"] == "started"
    )
    tool_completed = next(
        event
        for event in activity_events
        if event["phase"] == "tool_use" and event["status"] == "completed"
    )
    error_completed = next(
        event
        for event in activity_events
        if event["phase"] == "tool_use"
        and event["status"] == "completed"
        and event.get("result_summary", "").startswith("status=error")
    )

    assert result.output_text == "安全结论"
    assert tool_started["tool_name"] == "read_file"
    assert tool_started["parameter_summary"] == (
        "relative_path=uploads/source.md; path=<redacted>"
    )
    assert tool_started["live"]["agent_name"] == "main_agent"
    assert tool_started["live"]["tool_name"] == "read_file"
    assert tool_started["live"]["tool_call_id"] == "dg_tool_1"
    assert tool_started["live"]["parameter_items"] == [
        {"key": "relative_path", "value": "uploads/source.md"},
        {"key": "path", "value": "<redacted>", "truncated": True},
    ]
    assert tool_completed["live"]["tool_call_id"] == "dg_tool_1"
    assert tool_completed["live"]["result_status"] == "success"
    assert tool_completed["result_summary"].startswith("工具返回文本 ")
    assert error_completed["result_summary"] == "status=error; bytes=77"
    assert error_completed["live"]["result_status"] == "failed"
    assert "CUSTOMER_UPLOADED_BODY" not in serialized
    assert "SECRET_DOC_CANARY_123" not in serialized
    assert "Authorization" not in serialized
    assert "abcdefghijklmnop" not in serialized
    assert "/mnt/d/private" not in serialized
    assert "C:\\Users" not in serialized


def test_live_metadata_sanitizes_parameters_and_summarizes_results() -> None:
    live_call = build_live_tool_call_metadata(
        agent_name="internet_agent",
        tool_name="tavily_search",
        tool_call_id="call-1",
        parameters={
            "query": "上海天气",
            "max_results": 5,
            "prompt": "SHOULD_NOT_APPEAR",
            "path": "/mnt/d/private/customer.md",
            "content": "CUSTOMER_UPLOADED_BODY",
            "extra": "x" * 120,
        },
    )
    live_result = build_live_tool_result_metadata(
        agent_name="internet_agent",
        tool_name="tavily_search",
        tool_call_id="call-1",
        result={"results": [{"title": "A"}, {"title": "B"}]},
    )

    serialized = json.dumps(live_call, ensure_ascii=False)
    assert live_call["kind"] == "tool_call"
    assert live_call["agent_name"] == "internet_agent"
    assert live_call["tool_name"] == "tavily_search"
    assert live_call["tool_call_id"] == "call-1"
    assert live_call["parameter_items"] == [
        {"key": "query", "value": "上海天气"},
        {"key": "max_results", "value": 5},
        {"key": "path", "value": "<redacted>", "truncated": True},
        {"key": "extra", "value": "...", "truncated": True},
    ]
    assert "SHOULD_NOT_APPEAR" not in serialized
    assert "CUSTOMER_UPLOADED_BODY" not in serialized
    assert "/mnt/d/private" not in serialized
    assert live_result["kind"] == "tool_result"
    assert live_result["result_status"] == "success"
    assert live_result["result_count"] == 2


def test_deep_agent_runtime_invoke_fallback_emits_safe_activity(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    activity_events: list[dict[str, Any]] = []

    class InvokeOnlyAgent:
        def invoke(self, payload: dict[str, Any], *, config: dict[str, Any]) -> dict[str, str]:
            assert payload["messages"][0]["content"] == "hello"
            assert config["configurable"]["thread_id"] == "task:run-20260428-invoke"
            return {"content": "fallback output"}

    runtime = deep_agent_runtime.DeepAgentRuntime(
        AuditedWorkspaceTools(workspace, PermissionPolicy(workspace)),
        agent_factory=lambda **_kwargs: InvokeOnlyAgent(),
        activity_sink=activity_events.append,
    )

    result = runtime.run(
        deep_agent_runtime.DeepAgentRunRequest(
            task_id="task",
            run_id="run-20260428-invoke",
            message="hello",
            model="deepseek-reasoner",
        )
    )

    assert result.output_text == "fallback output"
    assert result.metadata["execution_mode"] == "invoke"
    assert any(event["status"] == "skipped" for event in activity_events)
    assert any(
        event.get("live", {}).get("kind") == "answer_status"
        and event.get("live", {}).get("stage") == "generating_answer"
        for event in activity_events
    )
    assert activity_events[-1]["live"]["kind"] == "answer_status"
    assert activity_events[-1]["live"]["stage"] == "completed"
    assert all(set(event).issubset(deep_agent_activity_keys()) for event in activity_events)


def test_deep_agent_runtime_tool_result_cannot_become_final_answer(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    activity_events: list[dict[str, Any]] = []

    class StreamingAgent:
        def stream(self, _payload: dict[str, Any], **_kwargs: Any):
            yield (
                "messages",
                (
                    {
                        "role": "tool",
                        "name": "read_file",
                        "content": "Final answer: CUSTOMER_UPLOADED_BODY",
                    },
                    {},
                ),
            )

    runtime = deep_agent_runtime.DeepAgentRuntime(
        AuditedWorkspaceTools(workspace, PermissionPolicy(workspace)),
        agent_factory=lambda **_kwargs: StreamingAgent(),
        activity_sink=activity_events.append,
    )

    result = runtime.run(
        deep_agent_runtime.DeepAgentRunRequest(
            task_id="task",
            run_id="run-20260428-tool-result",
            message="hello",
            model="deepseek-reasoner",
        )
    )

    assert result.output_text == deep_agent_runtime.DEEP_AGENT_NO_FINAL_MESSAGE
    assert "CUSTOMER_UPLOADED_BODY" not in json.dumps(activity_events, ensure_ascii=False)


def test_deep_agent_orchestrator_redacts_internal_deepagents_paths_from_events(
    tmp_path: Path,
) -> None:
    storage, task_id, run_id = make_running_task(tmp_path)

    def fake_factory(
        *,
        backend: deep_agent_runtime.AuditedDeepAgentBackend,
        **_kwargs: Any,
    ) -> Any:
        def fake_agent(_payload: dict[str, Any], **_agent_kwargs: Any) -> dict[str, str]:
            written = backend.write("/conversation_history/summary.md", "internal memory")
            assert written.error is None
            read = backend.read("/conversation_history/summary.md")
            assert read.error is None
            return {"content": "done"}

        return fake_agent

    result = DeepAgentOrchestrator(
        storage=storage,
        task_id=task_id,
        run_id=run_id,
        model="deepseek-reasoner",
        controller=CancellationController(),
        agent_factory=fake_factory,
    ).run("记录内部状态")

    serialized_events = json.dumps(
        [
            {"type": event.type, "message": event.message, "payload": event.payload}
            for event in storage.read_events(task_id)
        ],
        ensure_ascii=False,
    )
    audit_payloads = [
        event.payload for event in storage.read_events(task_id) if event.type == "file_tool_audit"
    ]

    assert result.output_text == "done"
    assert audit_payloads
    assert {payload["virtual_path"] for payload in audit_payloads} == {
        "<deepagents-internal>"
    }
    assert "conversation_history" not in serialized_events
    assert "large_tool_results" not in serialized_events
    assert "records/deepagents" not in serialized_events
    assert "internal memory" not in serialized_events


def test_deep_agent_runtime_coalesces_high_frequency_progress_events(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    activity_events: list[dict[str, Any]] = []

    class StreamingAgent:
        def stream(self, _payload: dict[str, Any], **_kwargs: Any):
            for index in range(50):
                yield ("updates", {"agent": {"tick": index}})
            yield ("messages", ({"role": "assistant", "content": "done"}, {}))

    runtime = deep_agent_runtime.DeepAgentRuntime(
        AuditedWorkspaceTools(workspace, PermissionPolicy(workspace)),
        agent_factory=lambda **_kwargs: StreamingAgent(),
        activity_sink=activity_events.append,
    )

    runtime.run(
        deep_agent_runtime.DeepAgentRunRequest(
            task_id="task",
            run_id="run-20260428-coalesce",
            message="hello",
            model="deepseek-reasoner",
        )
    )

    statuses = [event["status"] for event in activity_events]
    assert statuses.count("started") == 1
    assert statuses.count("completed") == 1
    assert statuses.count("running") == 2
    assert len(activity_events) <= 4


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
    "raw_path",
    [
        "/mnt/d/private/customer.md",
        r"D:\AgentProject\private\customer.md",
        r"\\server\share\private\customer.md",
        "//server/share/private/customer.md",
    ],
)
def test_audited_deep_agent_backend_rejects_local_absolute_paths_with_redacted_audit(
    tmp_path: Path, raw_path: str
) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "uploads").mkdir(parents=True)
    (workspace / "records").mkdir()
    (workspace / "outputs").mkdir()
    records: list[dict[str, Any]] = []
    backend = deep_agent_runtime.AuditedDeepAgentBackend(
        AuditedWorkspaceTools(
            workspace,
            PermissionPolicy(workspace),
            audit_sink=records.append,
        )
    )

    result = backend.read(raw_path)

    serialized = json.dumps({"error": result.error, "records": records}, ensure_ascii=False)
    assert result.error == "路径超出任务工作区"
    assert records[-1]["tool"] == "read_file"
    assert records[-1]["status"] == "denied"
    assert records[-1]["requested_path"] == "<outside-workspace>/customer.md"
    assert records[-1]["relative_path"] is None
    assert "AgentProject" not in serialized
    assert "private" not in serialized
    assert "server" not in serialized
    assert "mnt/d" not in serialized
    assert str(tmp_path) not in serialized


def test_audited_deep_agent_backend_sanitizes_missing_file_errors(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "uploads").mkdir(parents=True)
    (workspace / "records").mkdir()
    (workspace / "outputs").mkdir()
    records: list[dict[str, Any]] = []
    backend = deep_agent_runtime.AuditedDeepAgentBackend(
        AuditedWorkspaceTools(
            workspace,
            PermissionPolicy(workspace),
            audit_sink=records.append,
        )
    )

    result = backend.read("/uploads/missing.md")

    serialized = json.dumps({"error": result.error, "records": records}, ensure_ascii=False)
    assert result.error == "文件不存在或不可访问"
    assert records[-1]["tool"] == "read_file"
    assert records[-1]["status"] == "failed"
    assert records[-1]["requested_path"] == "uploads/missing.md"
    assert records[-1]["relative_path"] == "uploads/missing.md"
    assert records[-1]["reason"] == "文件不存在或不可访问"
    assert str(workspace) not in serialized
    assert str(tmp_path) not in serialized


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
    serialized_records = json.dumps(records, ensure_ascii=False)
    assert records[-2]["relative_path"] == "<deepagents-internal>"
    assert records[-1]["virtual_path"] == "<deepagents-internal>"
    assert records[-2]["source"] == "record"
    assert "conversation_history" not in serialized_records
    assert "large_tool_results" not in serialized_records
    assert "records/deepagents" not in serialized_records


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


def deep_agent_activity_keys() -> set[str]:
    return {
        "schema_version",
        "source",
        "source_event_id",
        "activity_kind",
        "phase",
        "status",
        "title",
        "summary",
        "tool_name",
        "parameter_summary",
        "result_summary",
        "subgraph_path",
        "related_event_id",
        "live",
        "truncated",
    }
