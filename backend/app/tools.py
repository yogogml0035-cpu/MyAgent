from __future__ import annotations

import hashlib
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import httpx

from .permissions import PermissionPolicy
from .runtime import CancellationController, run_cancellable_command

AuditStatus = Literal["success", "denied", "cancelled", "failed"]
AuditOperation = Literal["list", "read", "write", "glob", "grep"]
AuditSink = Callable[[dict[str, Any]], None]


@dataclass(frozen=True)
class FileToolAuditRecord:
    tool: str
    operation: AuditOperation
    requested_path: str
    relative_path: str | None
    status: AuditStatus
    reason: str
    bytes_count: int | None = None
    partial: bool = False
    sha256: str | None = None
    source: str = "output"
    promoted_artifact_id: str | None = None
    timestamp: str | None = None

    def to_payload(self) -> dict[str, Any]:
        timestamp = self.timestamp or utc_now()
        virtual_path = self.relative_path or self.requested_path
        return {
            "tool": self.tool,
            "tool_name": self.tool,
            "operation": self.operation,
            "op": self.operation,
            "requested_path": self.requested_path,
            "virtual_path": virtual_path,
            "relative_path": self.relative_path,
            "resolved_workspace_path": self.relative_path,
            "status": self.status,
            "reason": self.reason,
            "bytes": self.bytes_count,
            "sha256": self.sha256,
            "partial": self.partial,
            "source": self.source,
            "promoted_artifact_id": self.promoted_artifact_id,
            "timestamp": timestamp,
        }


class AuditedWorkspaceTools:
    """File tools for agent adapters that expose only workspace-relative paths."""

    def __init__(
        self,
        workspace_root: Path,
        policy: PermissionPolicy,
        controller: CancellationController | None = None,
        audit_sink: AuditSink | None = None,
        *,
        read_chunk_chars: int = 1024 * 1024,
        write_chunk_chars: int = 1024 * 1024,
        writable_roots: tuple[str, ...] = ("records", "outputs"),
    ) -> None:
        self.workspace_root = workspace_root.resolve()
        self.policy = policy
        self.controller = controller or CancellationController()
        self.audit_sink = audit_sink
        self.read_chunk_chars = max(1, read_chunk_chars)
        self.write_chunk_chars = max(1, write_chunk_chars)
        self.writable_roots = tuple(root.strip("/\\") for root in writable_roots if root.strip("/\\"))

    def list_dir(self, relative_path: str = ".") -> list[str]:
        requested_path = self._redact_requested_path(relative_path)
        resolved_path: str | None = None
        try:
            self.controller.raise_if_cancelled()
            path, resolved_path = self._resolve(relative_path)
            self._require_allowed(path, write=False)
            self.controller.raise_if_cancelled()
            entries = sorted(child.name for child in path.iterdir())
        except PermissionError as exc:
            self._audit(
                "list_dir",
                "list",
                requested_path,
                resolved_path,
                "denied",
                str(exc),
            )
            raise
        except RuntimeError as exc:
            if self.controller.is_cancelled():
                self._audit(
                    "list_dir",
                    "list",
                    requested_path,
                    resolved_path,
                    "cancelled",
                    str(exc),
                )
            else:
                self._audit(
                    "list_dir",
                    "list",
                    requested_path,
                    resolved_path,
                    "failed",
                    str(exc),
                )
            raise
        except Exception as exc:
            self._audit(
                "list_dir",
                "list",
                requested_path,
                resolved_path,
                "failed",
                str(exc),
            )
            raise
        self._audit(
            "list_dir",
            "list",
            requested_path,
            resolved_path,
            "success",
            "目录读取成功",
        )
        return entries

    def read_file(self, relative_path: str) -> str:
        requested_path = self._redact_requested_path(relative_path)
        resolved_path: str | None = None
        chunks: list[str] = []
        try:
            self.controller.raise_if_cancelled()
            path, resolved_path = self._resolve(relative_path)
            self._require_allowed(path, write=False)
            self.controller.raise_if_cancelled()
            with path.open(encoding="utf-8") as handle:
                while True:
                    self.controller.raise_if_cancelled()
                    chunk = handle.read(self.read_chunk_chars)
                    if not chunk:
                        break
                    chunks.append(chunk)
            text = "".join(chunks)
        except PermissionError as exc:
            self._audit(
                "read_file",
                "read",
                requested_path,
                resolved_path,
                "denied",
                str(exc),
                bytes_count=self._encoded_size(chunks),
                partial=bool(chunks),
            )
            raise
        except RuntimeError as exc:
            if self.controller.is_cancelled():
                self._audit(
                    "read_file",
                    "read",
                    requested_path,
                    resolved_path,
                    "cancelled",
                    str(exc),
                    bytes_count=self._encoded_size(chunks),
                    partial=bool(chunks),
                )
            else:
                self._audit(
                    "read_file",
                    "read",
                    requested_path,
                    resolved_path,
                    "failed",
                    str(exc),
                    bytes_count=self._encoded_size(chunks),
                    partial=bool(chunks),
                )
            raise
        except Exception as exc:
            self._audit(
                "read_file",
                "read",
                requested_path,
                resolved_path,
                "failed",
                str(exc),
                bytes_count=self._encoded_size(chunks),
                partial=bool(chunks),
            )
            raise
        self._audit(
            "read_file",
            "read",
            requested_path,
            resolved_path,
            "success",
            "文件读取成功",
            bytes_count=len(text.encode("utf-8")),
            sha256=sha256_text(text),
        )
        return text

    def write_file(self, relative_path: str, content: str) -> dict[str, Any]:
        requested_path = self._redact_requested_path(relative_path)
        resolved_path: str | None = None
        bytes_written = 0
        temp_path: Path | None = None
        try:
            self.controller.raise_if_cancelled()
            path, resolved_path = self._resolve(relative_path)
            self._require_allowed(path, write=True)
            self.controller.raise_if_cancelled()
            path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
            with temp_path.open("w", encoding="utf-8") as handle:
                for index in range(0, len(content), self.write_chunk_chars):
                    self.controller.raise_if_cancelled()
                    chunk = content[index : index + self.write_chunk_chars]
                    handle.write(chunk)
                    bytes_written += len(chunk.encode("utf-8"))
            self.controller.raise_if_cancelled()
            self._audit(
                "write_file",
                "write",
                requested_path,
                resolved_path,
                "success",
                "文件写入成功",
                bytes_count=bytes_written,
                sha256=sha256_text(content),
            )
            temp_path.replace(path)
            temp_path = None
        except PermissionError as exc:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
            self._audit(
                "write_file",
                "write",
                requested_path,
                resolved_path,
                "denied",
                str(exc),
                bytes_count=bytes_written,
                partial=bytes_written > 0,
            )
            raise
        except RuntimeError as exc:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
            if self.controller.is_cancelled():
                self._audit(
                    "write_file",
                    "write",
                    requested_path,
                    resolved_path,
                    "cancelled",
                    str(exc),
                    bytes_count=bytes_written,
                    partial=bytes_written > 0,
                )
            else:
                self._audit(
                    "write_file",
                    "write",
                    requested_path,
                    resolved_path,
                    "failed",
                    str(exc),
                    bytes_count=bytes_written,
                    partial=bytes_written > 0,
                )
            raise
        except Exception as exc:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
            self._audit(
                "write_file",
                "write",
                requested_path,
                resolved_path,
                "failed",
                str(exc),
                bytes_count=bytes_written,
                partial=bytes_written > 0,
            )
            raise
        return {"relative_path": resolved_path, "bytes": bytes_written}

    def audit_file_operation(
        self,
        tool: str,
        operation: AuditOperation,
        relative_path: str,
        status: AuditStatus,
        reason: str,
        *,
        bytes_count: int | None = None,
        partial: bool = False,
    ) -> None:
        requested_path = self._redact_requested_path(relative_path)
        resolved_path: str | None = None
        try:
            _, resolved_path = self._resolve(relative_path)
        except PermissionError:
            resolved_path = None
        self._audit(
            tool,
            operation,
            requested_path,
            resolved_path,
            status,
            reason,
            bytes_count=bytes_count,
            partial=partial,
        )

    def _resolve(self, relative_path: str) -> tuple[Path, str]:
        raw_path = relative_path or "."
        if is_windows_absolute_path(raw_path):
            raise PermissionError("路径超出任务工作区")
        candidate = Path(raw_path)
        path = (
            candidate.resolve()
            if candidate.is_absolute()
            else (self.workspace_root / raw_path).resolve()
        )
        if not self._is_within_workspace(path):
            raise PermissionError("路径超出任务工作区")
        return path, self._relative_path(path)

    def _require_allowed(self, path: Path, *, write: bool) -> None:
        decision = self.policy.classify_path_access(path, write=write)
        if decision.status != "allow":
            raise PermissionError(decision.reason)
        if write and not self._is_under_writable_root(path):
            allowed = " 或 ".join(self.writable_roots)
            raise PermissionError(f"DeepAgent 只能写入 {allowed} 目录")

    def _relative_path(self, path: Path) -> str:
        if path == self.workspace_root:
            return "."
        return path.relative_to(self.workspace_root).as_posix()

    def _redact_requested_path(self, relative_path: str) -> str:
        raw_path = str(relative_path or ".")
        if is_windows_absolute_path(raw_path):
            return f"<outside-workspace>/{windows_path_name(raw_path)}"
        candidate = Path(raw_path)
        try:
            path = (
                candidate.resolve()
                if candidate.is_absolute()
                else (self.workspace_root / raw_path).resolve()
            )
        except (OSError, RuntimeError, ValueError):
            path = None
        if path is not None and self._is_within_workspace(path):
            return self._relative_path(path)
        if candidate.is_absolute():
            return f"<outside-workspace>/{candidate.name or '<root>'}"
        return raw_path.replace("\\", "/")

    def _is_within_workspace(self, path: Path) -> bool:
        return path == self.workspace_root or self.workspace_root in path.parents

    def _audit(
        self,
        tool: str,
        operation: AuditOperation,
        requested_path: str,
        relative_path: str | None,
        status: AuditStatus,
        reason: str,
        *,
        bytes_count: int | None = None,
        partial: bool = False,
        sha256: str | None = None,
    ) -> None:
        if self.audit_sink is None:
            return
        source = source_for_relative_path(relative_path)
        self.audit_sink(
            FileToolAuditRecord(
                tool=tool,
                operation=operation,
                requested_path=requested_path,
                relative_path=relative_path,
                status=status,
                reason=reason,
                bytes_count=bytes_count,
                partial=partial,
                sha256=sha256,
                source=source,
            ).to_payload()
        )

    @staticmethod
    def _encoded_size(chunks: list[str]) -> int:
        return sum(len(chunk.encode("utf-8")) for chunk in chunks)

    def _is_under_writable_root(self, path: Path) -> bool:
        if not self.writable_roots:
            return False
        return any(
            path == (self.workspace_root / root).resolve()
            or (self.workspace_root / root).resolve() in path.parents
            for root in self.writable_roots
        )


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def source_for_relative_path(relative_path: str | None) -> str:
    if relative_path is None:
        return "output"
    if relative_path == "uploads" or relative_path.startswith("uploads/"):
        return "upload_snapshot"
    if relative_path == "records" or relative_path.startswith("records/"):
        return "record"
    return "output"


def is_windows_absolute_path(raw_path: str) -> bool:
    normalized = raw_path.replace("/", "\\")
    return (
        len(normalized) >= 3
        and normalized[1] == ":"
        and normalized[0].isalpha()
        and normalized[2] == "\\"
    ) or normalized.startswith("\\\\")


def windows_path_name(raw_path: str) -> str:
    stripped = raw_path.rstrip("\\/")
    normalized = stripped.replace("/", "\\")
    name = normalized.rsplit("\\", 1)[-1]
    return name or "<root>"


class WorkspaceTools:
    def __init__(
        self,
        workspace_root: Path,
        policy: PermissionPolicy,
        tavily_api_key: str | None,
        controller: CancellationController | None = None,
    ):
        self.workspace_root = workspace_root.resolve()
        self.policy = policy
        self.tavily_api_key = tavily_api_key
        self.controller = controller or CancellationController()

    def list_dir(self, relative_path: str = ".") -> list[str]:
        path = self._resolve(relative_path)
        decision = self.policy.classify_path_access(path)
        if decision.status != "allow":
            raise PermissionError(decision.reason)
        return sorted(child.name for child in path.iterdir())

    def read_file(self, relative_path: str) -> str:
        path = self._resolve(relative_path)
        decision = self.policy.classify_path_access(path)
        if decision.status != "allow":
            raise PermissionError(decision.reason)
        return path.read_text(encoding="utf-8")

    def full_text_search(self, query: str, suffix: str = ".md") -> list[dict[str, Any]]:
        self.controller.raise_if_cancelled()
        results: list[dict[str, Any]] = []
        for path in self.workspace_root.rglob(f"*{suffix}"):
            self.controller.raise_if_cancelled()
            text = path.read_text(encoding="utf-8", errors="ignore")
            for line_number, line in enumerate(text.splitlines(), start=1):
                if query.lower() in line.lower():
                    results.append(
                        {
                            "file": str(path.relative_to(self.workspace_root)),
                            "line": line_number,
                            "snippet": line.strip()[:240],
                        }
                    )
        return results

    def write_markdown(self, relative_path: str, content: str) -> Path:
        path = self._resolve(relative_path)
        if path.suffix.lower() != ".md":
            raise ValueError("write_markdown 只能写入 .md 文件")
        decision = self.policy.classify_path_access(path, write=True)
        if decision.status != "allow":
            raise PermissionError(decision.reason)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def write_python_script(self, relative_path: str, content: str) -> Path:
        path = self._resolve(relative_path)
        if path.suffix.lower() != ".py":
            raise ValueError("write_python_script 只能写入 .py 文件")
        decision = self.policy.classify_path_access(path, write=True)
        if decision.status != "allow":
            raise PermissionError(decision.reason)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def run_tests(self, command: list[str] | None = None) -> dict[str, Any]:
        command = command or ["uv", "run", "pytest"]
        decision = self.policy.classify_command(command)
        if decision.status != "allow":
            raise PermissionError(decision.reason)
        result = run_cancellable_command(
            command,
            cwd=str(self.workspace_root),
            timeout=120,
            controller=self.controller,
        )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout[-8000:],
            "stderr": result.stderr[-8000:],
        }

    def tavily_search(self, query: str, max_results: int = 5) -> dict[str, Any]:
        self.controller.raise_if_cancelled()
        if not self.tavily_api_key:
            return {"results": [], "warning": "未配置 TAVILY_API_KEY"}
        response = httpx.post(
            "https://api.tavily.com/search",
            json={"api_key": self.tavily_api_key, "query": query, "max_results": max_results},
            timeout=20,
        )
        self.controller.raise_if_cancelled()
        response.raise_for_status()
        return response.json()

    def _resolve(self, relative_path: str) -> Path:
        path = (self.workspace_root / relative_path).resolve()
        if not (path == self.workspace_root or self.workspace_root in path.parents):
            raise PermissionError("路径超出任务工作区")
        return path
