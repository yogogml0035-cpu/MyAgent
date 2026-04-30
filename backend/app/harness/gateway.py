from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from app.analysis import Emit, run_bid_analysis
from app.contracts import (
    ExecutionGateway,
    ExecutionHandle,
    ExecutionResult,
    ResourceKind,
    ResourceRef,
    ToolSpec,
    build_artifact_ref,
    build_upload_resource_ref,
)
from app.deep_agent_runtime import DeepAgentRunResult
from app.model_provider import ModelProvider
from app.orchestrator import DeepAgentOrchestrator
from app.permissions import PermissionPolicy
from app.runtime import CancellationController
from app.settings import Settings
from app.storage import TaskStorage
from app.tools import WorkspaceTools

GatewayExecutor = Callable[[ExecutionHandle, dict[str, Any]], ExecutionResult | dict[str, Any] | str]


@dataclass(frozen=True)
class GatewayTool:
    spec: ToolSpec
    executor: GatewayExecutor


class LegacyExecutionGateway(ExecutionGateway):
    """Compatibility gateway for existing execution abilities.

    The legacy gateway is intentionally not wired into TaskRunner yet. It gives
    future HarnessEngine work one common execution surface while preserving the
    current production call graph.
    """

    def __init__(self, tools: list[GatewayTool]) -> None:
        self._tools = {tool.spec.name: tool for tool in tools}
        self._handles: set[str] = set()

    @classmethod
    def with_default_specs(
        cls,
        *,
        web_search: GatewayExecutor | None = None,
        analyze_documents: GatewayExecutor | None = None,
        deep_agent_run: GatewayExecutor | None = None,
    ) -> LegacyExecutionGateway:
        tools: list[GatewayTool] = []
        if web_search is not None:
            tools.append(
                GatewayTool(
                    ToolSpec(
                        name="web.search",
                        description="Run the existing Tavily-backed web search adapter.",
                        input_schema={
                            "type": "object",
                            "properties": {
                                "query": {"type": "string"},
                                "max_results": {"type": "integer"},
                            },
                            "required": ["query"],
                        },
                        capability_tags=("search", "web"),
                        timeout_seconds=20,
                    ),
                    web_search,
                )
            )
        if analyze_documents is not None:
            tools.append(
                GatewayTool(
                    ToolSpec(
                        name="bid.analyze_documents",
                        description="Run the existing deterministic bid document analysis path.",
                        input_schema={
                            "type": "object",
                            "properties": {
                                "task_message": {"type": "string"},
                                "model": {"type": "string"},
                            },
                            "required": ["task_message", "model"],
                        },
                        capability_tags=("analysis", "bid"),
                        timeout_seconds=120,
                    ),
                    analyze_documents,
                )
            )
        if deep_agent_run is not None:
            tools.append(
                GatewayTool(
                    ToolSpec(
                        name="deep_agent.run",
                        description="Run the existing task-scoped DeepAgent orchestrator adapter.",
                        input_schema={
                            "type": "object",
                            "properties": {
                                "message": {"type": "string"},
                                "model": {"type": "string"},
                            },
                            "required": ["message", "model"],
                        },
                        capability_tags=("agent", "deep-agent"),
                        timeout_seconds=120,
                        visible_to_model=False,
                    ),
                    deep_agent_run,
                )
            )
        return cls(tools)

    def list_tools(self, session_id: str) -> list[ToolSpec]:
        return sorted((tool.spec for tool in self._tools.values()), key=lambda spec: spec.name)

    def provision(
        self,
        session_id: str,
        *,
        resources: list[ResourceRef],
        requirements: dict[str, Any] | None = None,
    ) -> ExecutionHandle:
        handle = ExecutionHandle(
            id=f"exec-{uuid.uuid4().hex}",
            executor="legacy",
            resources=tuple(resources),
            metadata={
                "session_id": session_id,
                "requirements": dict(requirements or {}),
            },
        )
        self._handles.add(handle.id)
        return handle

    def execute(
        self,
        handle: ExecutionHandle,
        tool_name: str,
        tool_input: dict[str, Any],
    ) -> ExecutionResult:
        if handle.id not in self._handles:
            return ExecutionResult(
                status="denied",
                error="execution handle is not active",
                raw_error_type="InactiveExecutionHandle",
            )
        tool = self._tools.get(tool_name)
        if tool is None:
            return ExecutionResult(
                status="denied",
                error=f"tool is not registered: {tool_name}",
                raw_error_type="UnknownTool",
            )
        try:
            return _coerce_execution_result(tool.executor(handle, tool_input))
        except PermissionError as exc:
            return ExecutionResult(
                status="denied",
                error=str(exc),
                raw_error_type=type(exc).__name__,
            )
        except TimeoutError as exc:
            return ExecutionResult(
                status="timeout",
                error=str(exc),
                raw_error_type=type(exc).__name__,
            )
        except RuntimeError as exc:
            if "取消" in str(exc) or "cancel" in str(exc).lower():
                return ExecutionResult(
                    status="cancelled",
                    error=str(exc),
                    raw_error_type=type(exc).__name__,
                )
            return ExecutionResult(
                status="failed",
                error=str(exc),
                raw_error_type=type(exc).__name__,
            )
        except Exception as exc:
            return ExecutionResult(
                status="failed",
                error=str(exc),
                raw_error_type=type(exc).__name__,
            )

    def dispose(self, handle: ExecutionHandle) -> None:
        self._handles.discard(handle.id)


def upload_resource_ref(path: Path, *, session_id: str) -> ResourceRef:
    return _path_resource_ref(path, session_id=session_id, kind="upload")


def artifact_resource_ref(name: str, *, session_id: str, run_id: str) -> ResourceRef:
    return build_artifact_ref(
        session_id=session_id,
        run_id=run_id,
        name=name,
        artifact_type="text",
    ).resource


def legacy_web_search_executor(
    *,
    storage: TaskStorage,
    settings: Settings,
    controller: CancellationController,
) -> GatewayExecutor:
    def execute(handle: ExecutionHandle, tool_input: dict[str, Any]) -> ExecutionResult:
        session_id = str(handle.metadata.get("session_id") or "")
        query = str(tool_input.get("query") or "")
        max_results = _optional_positive_int(tool_input.get("max_results"), default=5)
        workspace_tools = WorkspaceTools(
            storage.task_dir(session_id),
            PermissionPolicy(storage.task_dir(session_id)),
            settings.tavily_api_key,
            controller,
        )
        result = workspace_tools.tavily_search(query, max_results=max_results)
        warning = result.get("warning")
        return ExecutionResult(
            status="failed" if isinstance(warning, str) and warning else "success",
            data=result,
            error=warning if isinstance(warning, str) else None,
            raw_error_type="MissingTavilyApiKey" if isinstance(warning, str) and warning else None,
        )

    return execute


def legacy_bid_analysis_executor(
    *,
    task_id: str,
    run_id: str,
    uploads: list[Path],
    model_provider: ModelProvider,
    storage: TaskStorage,
    controller: CancellationController,
    settings: Settings,
    emit: Emit,
) -> GatewayExecutor:
    def execute(handle: ExecutionHandle, tool_input: dict[str, Any]) -> ExecutionResult:
        task_message = str(tool_input.get("task_message") or "")
        model = str(tool_input.get("model") or "")
        result = run_bid_analysis(
            task_id=task_id,
            run_id=run_id,
            uploads=uploads,
            task_message=task_message,
            model=model,
            model_provider=model_provider,
            storage=storage,
            controller=controller,
            workspace_tools=WorkspaceTools(
                storage.task_dir(task_id),
                PermissionPolicy(storage.task_dir(task_id)),
                settings.tavily_api_key,
                controller,
            ),
            emit=emit,
        )
        return ExecutionResult(status="success", data=result)

    return execute


def legacy_deep_agent_executor(
    *,
    storage: TaskStorage,
    task_id: str,
    run_id: str,
    model: str,
    controller: CancellationController,
    uploads: list[Path] | None = None,
) -> GatewayExecutor:
    def execute(handle: ExecutionHandle, tool_input: dict[str, Any]) -> ExecutionResult:
        message = str(tool_input.get("message") or "")
        orchestrator = DeepAgentOrchestrator(
            storage=storage,
            task_id=task_id,
            run_id=run_id,
            model=str(tool_input.get("model") or model),
            controller=controller,
            uploads=uploads or [],
        )
        result = orchestrator.run(message)
        return _deep_agent_result_to_execution_result(result)

    return execute


def _path_resource_ref(path: Path, *, session_id: str, kind: ResourceKind) -> ResourceRef:
    if kind != "upload":
        return ResourceRef(
            id=f"{kind}:{session_id}:{path.name}",
            kind=kind,
            uri=f"myagent://sessions/{session_id}/resources/{path.name}",
            name=path.name,
            size_bytes=path.stat().st_size if path.exists() else None,
            metadata={"session_id": session_id},
        )
    return build_upload_resource_ref(
        session_id=session_id,
        filename=path.name,
        size_bytes=path.stat().st_size if path.exists() else None,
    )


def _coerce_execution_result(value: ExecutionResult | dict[str, Any] | str) -> ExecutionResult:
    if isinstance(value, ExecutionResult):
        return value
    if isinstance(value, str):
        return ExecutionResult(status="success", output=value)
    return ExecutionResult(status="success", data=dict(value))


def _deep_agent_result_to_execution_result(result: DeepAgentRunResult) -> ExecutionResult:
    status: Literal["success", "failed"] = (
        "success" if result.status in {"complete", "success"} else "failed"
    )
    return ExecutionResult(
        status=status,
        output=result.output_text,
        data=dict(result.metadata),
        error=None if status == "success" else result.output_text,
        raw_error_type=None if status == "success" else "DeepAgentRunFailed",
    )


def _optional_positive_int(value: object, *, default: int) -> int:
    if not isinstance(value, (str, bytes, int)):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default
