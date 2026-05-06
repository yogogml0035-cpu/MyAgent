from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import app.harness.gateway as gateway_module
from app.contracts import ExecutionGateway, ExecutionHandle, ExecutionResult, ResourceRef
from app.deep_agent_runtime import DeepAgentRunResult
from app.harness import (
    LegacyExecutionGateway,
    artifact_resource_ref,
    legacy_bid_analysis_executor,
    legacy_deep_agent_executor,
    legacy_web_search_executor,
    upload_resource_ref,
)
from app.runtime import CancellationController
from app.settings import Settings
from app.storage import TaskStorage


def test_legacy_execution_gateway_registers_default_tool_specs() -> None:
    gateway = LegacyExecutionGateway.with_default_specs(
        web_search=lambda handle, tool_input: {"results": []},
        analyze_documents=lambda handle, tool_input: {"evidence_count": 0},
        deep_agent_run=lambda handle, tool_input: "done",
    )

    specs = gateway.list_tools("session-1")

    assert isinstance(gateway, ExecutionGateway)
    assert [spec.name for spec in specs] == [
        "bid.analyze_documents",
        "deep_agent.run",
        "web.search",
    ]
    assert specs[0].capability_tags == ("analysis", "bid")
    assert specs[2].input_schema["required"] == ["query"]


def test_legacy_execution_gateway_provisions_executes_and_disposes(tmp_path) -> None:
    upload = tmp_path / "secret-plan.md"
    upload.write_text("hello", encoding="utf-8")
    resource = upload_resource_ref(upload, session_id="session-1")
    calls: list[tuple[str, str, dict[str, object]]] = []

    def web_search(handle, tool_input):
        calls.append((handle.id, handle.resources[0].uri, dict(tool_input)))
        return ExecutionResult(status="success", output="ok", data={"result_count": 1})

    gateway = LegacyExecutionGateway.with_default_specs(web_search=web_search)
    handle = gateway.provision(
        "session-1",
        resources=[resource],
        requirements={"route": "search"},
    )

    result = gateway.execute(handle, "web.search", {"query": "weather"})
    gateway.dispose(handle)
    denied = gateway.execute(handle, "web.search", {"query": "weather"})

    assert result.status == "success"
    assert result.output == "ok"
    assert result.data == {"result_count": 1}
    assert calls == [(handle.id, resource.uri, {"query": "weather"})]
    assert handle.metadata == {
        "session_id": "session-1",
        "requirements": {"route": "search"},
    }
    assert denied.status == "denied"
    assert denied.raw_error_type == "InactiveExecutionHandle"


def test_legacy_execution_gateway_maps_errors_to_result_status() -> None:
    gateway = LegacyExecutionGateway.with_default_specs(
        web_search=lambda handle, tool_input: (_ for _ in ()).throw(
            PermissionError("not allowed")
        ),
        analyze_documents=lambda handle, tool_input: (_ for _ in ()).throw(
            TimeoutError("too slow")
        ),
        deep_agent_run=lambda handle, tool_input: (_ for _ in ()).throw(
            RuntimeError("任务已取消")
        ),
    )
    handle = gateway.provision("session-1", resources=[])

    denied = gateway.execute(handle, "web.search", {})
    timeout = gateway.execute(handle, "bid.analyze_documents", {})
    cancelled = gateway.execute(handle, "deep_agent.run", {})
    unknown = gateway.execute(handle, "missing.tool", {})

    assert denied.status == "denied"
    assert denied.raw_error_type == "PermissionError"
    assert timeout.status == "timeout"
    assert timeout.raw_error_type == "TimeoutError"
    assert cancelled.status == "cancelled"
    assert cancelled.raw_error_type == "RuntimeError"
    assert unknown.status == "denied"
    assert unknown.raw_error_type == "UnknownTool"


def test_resource_refs_use_virtual_uris_without_absolute_paths(tmp_path) -> None:
    upload = tmp_path / "customer-secret.md"
    upload.write_text("sensitive", encoding="utf-8")

    upload_ref = upload_resource_ref(upload, session_id="session-1")
    artifact_ref = artifact_resource_ref(
        "../report.html",
        session_id="session-1",
        run_id="run-1",
    )

    assert isinstance(upload_ref, ResourceRef)
    assert upload_ref.kind == "upload"
    assert upload_ref.uri == "myagent://sessions/session-1/resources/customer-secret.md"
    assert str(tmp_path) not in upload_ref.uri
    assert str(Path.cwd()) not in upload_ref.uri
    assert upload_ref.size_bytes == len("sensitive")
    assert artifact_ref.kind == "artifact"
    assert artifact_ref.uri == "myagent://sessions/session-1/runs/run-1/artifacts/report.html"


def test_legacy_web_search_executor_wraps_existing_workspace_tool(tmp_path) -> None:
    storage = TaskStorage(tmp_path / "sessions")
    state = storage.create_task(None, "deepseek-reasoner")
    settings = Settings(
        task_root=tmp_path / "sessions",
        deepseek_api_key=None,
        deepseek_base_url="https://api.deepseek.com",
        tavily_api_key=None,
        workspace_root=tmp_path / "sessions",
    )
    executor = legacy_web_search_executor(
        storage=storage,
        settings=settings,
        controller=CancellationController(),
    )
    handle = ExecutionHandle(
        id="exec-1",
        executor="legacy",
        metadata={"session_id": state.task_id},
    )

    result = executor(handle, {"query": "天气", "max_results": 3})

    assert isinstance(result, ExecutionResult)
    assert result.status == "failed"
    assert result.error == "未配置 TAVILY_API_KEY"
    assert result.raw_error_type == "MissingTavilyApiKey"


def test_legacy_bid_analysis_executor_wraps_run_bid_analysis(monkeypatch, tmp_path) -> None:
    storage = TaskStorage(tmp_path / "sessions")
    calls: list[dict[str, object]] = []

    class FakeModelProvider:
        def chat(
            self,
            message: str,
            model: str,
            controller: CancellationController | None = None,
            *,
            on_delta: Callable[[str], None] | None = None,
        ) -> str:
            if on_delta is not None:
                on_delta("chat")
            return "chat"

        def reason(
            self,
            prompt: str,
            model: str,
            controller: CancellationController | None = None,
        ) -> str:
            return "reason"

    def fake_run_bid_analysis(**kwargs):
        calls.append(kwargs)
        kwargs["emit"]("plan_created", "计划已创建。", {"ok": True})
        return {"evidence_count": 2}

    monkeypatch.setattr(gateway_module, "run_bid_analysis", fake_run_bid_analysis)
    executor = legacy_bid_analysis_executor(
        task_id="task-1",
        run_id="run-1",
        uploads=[tmp_path / "a.md"],
        model_provider=FakeModelProvider(),
        storage=storage,
        controller=CancellationController(),
        settings=Settings(
            task_root=tmp_path / "sessions",
            deepseek_api_key=None,
            deepseek_base_url="https://api.deepseek.com",
            tavily_api_key=None,
            workspace_root=tmp_path / "sessions",
        ),
        emit=lambda event_type, message, payload: calls.append(
            {"event_type": event_type, "message": message, "payload": payload}
        ),
    )

    result = executor(
        ExecutionHandle(id="exec-1", executor="legacy"),
        {"task_message": "分析投标文件", "model": "deepseek-reasoner"},
    )

    assert isinstance(result, ExecutionResult)
    assert result.status == "success"
    assert result.data == {"evidence_count": 2}
    assert calls[0]["task_id"] == "task-1"
    assert calls[0]["run_id"] == "run-1"
    assert calls[0]["task_message"] == "分析投标文件"
    assert calls[1]["event_type"] == "plan_created"


def test_legacy_deep_agent_executor_wraps_orchestrator(monkeypatch, tmp_path) -> None:
    calls: list[dict[str, object]] = []

    class FakeDeepAgentOrchestrator:
        def __init__(self, **kwargs) -> None:
            calls.append(kwargs)

        def run(self, message: str) -> DeepAgentRunResult:
            calls.append({"message": message})
            return DeepAgentRunResult(
                status="complete",
                output_text="完成",
                metadata={"promoted_artifacts": ["report.html"]},
            )

    monkeypatch.setattr(gateway_module, "DeepAgentOrchestrator", FakeDeepAgentOrchestrator)
    executor = legacy_deep_agent_executor(
        storage=TaskStorage(tmp_path / "sessions"),
        task_id="task-1",
        run_id="run-1",
        model="deepseek-reasoner",
        controller=CancellationController(),
        uploads=[tmp_path / "a.md"],
    )

    result = executor(
        ExecutionHandle(id="exec-1", executor="legacy"),
        {"message": "整理文件", "model": "deepseek-reasoner"},
    )

    assert isinstance(result, ExecutionResult)
    assert result.status == "success"
    assert result.output == "完成"
    assert result.data == {"promoted_artifacts": ["report.html"]}
    assert calls[0]["task_id"] == "task-1"
    assert calls[0]["run_id"] == "run-1"
    assert calls[1] == {"message": "整理文件"}
