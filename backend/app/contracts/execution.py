from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

from .resources import ResourceRef
from .security import CredentialRef

ExecutionStatus = Literal["success", "failed", "denied", "cancelled", "timeout"]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    capability_tags: tuple[str, ...] = ()
    requires_approval: bool = False
    timeout_seconds: int = 120
    visible_to_model: bool = True


@dataclass(frozen=True)
class ExecutionHandle:
    id: str
    executor: str
    resources: tuple[ResourceRef, ...] = ()
    credential_refs: tuple[CredentialRef, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExecutionResult:
    status: ExecutionStatus
    output: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    artifacts: tuple[ResourceRef, ...] = ()
    error: str | None = None
    raw_error_type: str | None = None


@runtime_checkable
class ExecutionGateway(Protocol):
    def list_tools(self, session_id: str) -> list[ToolSpec]:
        ...

    def provision(
        self,
        session_id: str,
        *,
        resources: list[ResourceRef],
        requirements: dict[str, Any] | None = None,
    ) -> ExecutionHandle:
        ...

    def execute(
        self,
        handle: ExecutionHandle,
        tool_name: str,
        tool_input: dict[str, Any],
    ) -> ExecutionResult:
        ...

    def dispose(self, handle: ExecutionHandle) -> None:
        ...
