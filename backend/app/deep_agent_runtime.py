from __future__ import annotations

import asyncio
import fnmatch
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .runtime import CancellationController
from .tools import AuditedWorkspaceTools

try:
    from deepagents import create_deep_agent as _imported_create_deep_agent
except ImportError:  # pragma: no cover - optional integration dependency.
    _imported_create_deep_agent = None

try:
    from deepagents.backends.protocol import BackendProtocol as ImportedBackendProtocol
except ImportError:  # pragma: no cover - optional integration dependency.
    ImportedBackendProtocol = object


@dataclass
class ReadResult:
    error: str | None = None
    file_data: dict[str, Any] | None = None


@dataclass
class WriteResult:
    error: str | None = None
    path: str | None = None
    files_update: dict[str, Any] | None = None


@dataclass
class EditResult:
    error: str | None = None
    path: str | None = None
    files_update: dict[str, Any] | None = None
    occurrences: int | None = None


@dataclass
class LsResult:
    error: str | None = None
    entries: list[dict[str, Any]] | None = None


@dataclass
class GrepResult:
    error: str | None = None
    matches: list[dict[str, Any]] | None = None


@dataclass
class GlobResult:
    error: str | None = None
    matches: list[dict[str, Any]] | None = None


@dataclass
class FileDownloadResponse:
    path: str
    content: bytes | None = None
    error: str | None = None


@dataclass
class FileUploadResponse:
    path: str
    error: str | None = None

AgentFactory = Callable[..., Any]
_DEFAULT_AGENT_FACTORY: AgentFactory | None = _imported_create_deep_agent
DEEPAGENTS_INTERNAL_PREFIXES = ("large_tool_results", "conversation_history")


class AuditedDeepAgentBackend(ImportedBackendProtocol):
    """DeepAgents backend protocol implementation backed by audited task tools."""

    def __init__(self, file_tools: AuditedWorkspaceTools) -> None:
        self.file_tools = file_tools
        self.virtual_mode = True
        self.audited = True

    def ls(self, path: str) -> LsResult:
        try:
            relative_path = self._relative_virtual_path(path)
            names = self.file_tools.list_dir(relative_path)
            entries = [
                self._file_info(self._join_relative(relative_path, name))
                for name in names
            ]
            return LsResult(entries=entries)
        except Exception as exc:
            return LsResult(error=str(exc))

    async def als(self, path: str) -> LsResult:
        return await asyncio.to_thread(self.ls, path)

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:
        try:
            relative_path = self._relative_virtual_path(file_path)
            content = self.file_tools.read_file(relative_path)
            selected = "\n".join(content.splitlines()[offset : offset + limit])
            return ReadResult(
                file_data={
                    "content": selected,
                    "encoding": "utf-8",
                }
            )
        except Exception as exc:
            return ReadResult(error=str(exc))

    async def aread(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:
        return await asyncio.to_thread(self.read, file_path, offset, limit)

    def grep(
        self, pattern: str, path: str | None = None, glob: str | None = None
    ) -> GrepResult:
        relative_root = self._relative_virtual_path(path or "/")
        try:
            matches: list[dict[str, Any]] = []
            for file_path in self._iter_files(relative_root, glob):
                relative_path = file_path.relative_to(self.file_tools.workspace_root).as_posix()
                text = self.file_tools.read_file(relative_path)
                for line_number, line in enumerate(text.splitlines(), start=1):
                    if pattern in line:
                        matches.append(
                            {
                                "path": self._virtual_path(relative_path),
                                "line": line_number,
                                "text": line,
                            }
                        )
            self.file_tools.audit_file_operation(
                "grep", "grep", relative_root, "success", "文件内容检索成功", bytes_count=len(matches)
            )
            return GrepResult(matches=matches)
        except Exception as exc:
            self.file_tools.audit_file_operation(
                "grep", "grep", relative_root, "failed", str(exc)
            )
            return GrepResult(error=str(exc))

    async def agrep(
        self, pattern: str, path: str | None = None, glob: str | None = None
    ) -> GrepResult:
        return await asyncio.to_thread(self.grep, pattern, path, glob)

    def glob(self, pattern: str, path: str = "/") -> GlobResult:
        relative_root = self._relative_virtual_path(path)
        try:
            matches = [
                self._file_info(file_path.relative_to(self.file_tools.workspace_root).as_posix())
                for file_path in self._iter_files(relative_root, pattern)
            ]
            self.file_tools.audit_file_operation(
                "glob",
                "glob",
                relative_root,
                "success",
                "文件名匹配成功",
                bytes_count=len(matches),
            )
            return GlobResult(matches=matches)
        except Exception as exc:
            self.file_tools.audit_file_operation(
                "glob", "glob", relative_root, "failed", str(exc)
            )
            return GlobResult(error=str(exc))

    async def aglob(self, pattern: str, path: str = "/") -> GlobResult:
        return await asyncio.to_thread(self.glob, pattern, path)

    def write(self, file_path: str, content: str) -> WriteResult:
        try:
            relative_path = self._relative_virtual_path(file_path)
            path = self._workspace_path(relative_path)
            if path.exists():
                return WriteResult(error=f"文件已存在：{file_path}")
            result = self.file_tools.write_file(relative_path, content)
            return WriteResult(path=self._virtual_path(str(result["relative_path"])))
        except Exception as exc:
            return WriteResult(error=str(exc))

    async def awrite(self, file_path: str, content: str) -> WriteResult:
        return await asyncio.to_thread(self.write, file_path, content)

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        try:
            if old_string == new_string:
                return EditResult(error="替换内容不能与原内容相同")
            relative_path = self._relative_virtual_path(file_path)
            original = self.file_tools.read_file(relative_path)
            occurrences = original.count(old_string)
            if occurrences == 0:
                return EditResult(error="未找到要替换的内容")
            if not replace_all and occurrences != 1:
                return EditResult(error="要替换的内容不唯一")
            updated = original.replace(
                old_string, new_string, occurrences if not replace_all else -1
            )
            self.file_tools.write_file(relative_path, updated)
            return EditResult(path=file_path, occurrences=occurrences)
        except Exception as exc:
            return EditResult(error=str(exc))

    async def aedit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        return await asyncio.to_thread(
            self.edit, file_path, old_string, new_string, replace_all
        )

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        responses: list[FileUploadResponse] = []
        for path, content in files:
            try:
                text = content.decode("utf-8")
            except UnicodeDecodeError:
                responses.append(FileUploadResponse(path=path, error="文件必须使用 UTF-8 编码"))
                continue
            result = self.write(path, text)
            responses.append(FileUploadResponse(path=path, error=result.error))
        return responses

    async def aupload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        return await asyncio.to_thread(self.upload_files, files)

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        responses: list[FileDownloadResponse] = []
        for path in paths:
            result = self.read(path, offset=0, limit=1_000_000)
            if result.error or result.file_data is None:
                responses.append(FileDownloadResponse(path=path, error=result.error))
                continue
            responses.append(
                FileDownloadResponse(
                    path=path,
                    content=str(result.file_data["content"]).encode("utf-8"),
                )
            )
        return responses

    async def adownload_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        return await asyncio.to_thread(self.download_files, paths)

    def _relative_virtual_path(self, raw_path: str) -> str:
        normalized = raw_path.strip() or "/"
        if not normalized.startswith("/"):
            normalized = f"/{normalized}"
        candidate = normalized.lstrip("/")
        for prefix in DEEPAGENTS_INTERNAL_PREFIXES:
            if candidate == prefix or candidate.startswith(f"{prefix}/"):
                return f"records/deepagents/{candidate}"
        return candidate or "."

    def _join_relative(self, relative_path: str, name: str) -> str:
        if relative_path == ".":
            return name
        return f"{relative_path.rstrip('/')}/{name}"

    def _file_info(self, relative_path: str) -> dict[str, Any]:
        path = self._workspace_path(relative_path)
        info: dict[str, Any] = {
            "path": self._virtual_path(relative_path),
            "is_dir": path.is_dir(),
        }
        if path.exists():
            stat = path.stat()
            info["size"] = stat.st_size
            info["modified_at"] = datetime_from_timestamp(stat.st_mtime)
        return info

    def _iter_files(self, relative_root: str, pattern: str | None) -> list[Path]:
        root = self._workspace_path(relative_root)
        if not root.exists():
            return []
        files = sorted(path for path in root.rglob("*") if path.is_file())
        if not pattern:
            return files
        return [
            path
            for path in files
            if fnmatch.fnmatch(path.relative_to(root).as_posix(), pattern)
            or fnmatch.fnmatch(path.relative_to(self.file_tools.workspace_root).as_posix(), pattern)
        ]

    def _virtual_path(self, relative_path: str) -> str:
        normalized = relative_path.strip("/").replace("\\", "/")
        internal_prefix = "records/deepagents/"
        if normalized.startswith(internal_prefix):
            stripped = normalized[len(internal_prefix) :]
            if any(
                stripped == prefix or stripped.startswith(f"{prefix}/")
                for prefix in DEEPAGENTS_INTERNAL_PREFIXES
            ):
                return "/" + stripped
        return "/" + normalized

    def _workspace_path(self, relative_path: str) -> Path:
        path = (self.file_tools.workspace_root / relative_path).resolve()
        if not (path == self.file_tools.workspace_root or self.file_tools.workspace_root in path.parents):
            raise PermissionError("路径超出任务工作区")
        return path


class DeepAgentUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class DeepAgentRunRequest:
    task_id: str
    run_id: str
    message: str
    model: str


@dataclass(frozen=True)
class DeepAgentRunResult:
    status: str
    output_text: str
    metadata: dict[str, Any]


class DeepAgentRuntime:
    def __init__(
        self,
        file_tools: AuditedWorkspaceTools,
        *,
        agent_factory: AgentFactory | None = None,
    ) -> None:
        self.file_tools = file_tools
        self.agent_factory = agent_factory if agent_factory is not None else _DEFAULT_AGENT_FACTORY

    @property
    def is_available(self) -> bool:
        return self.agent_factory is not None

    def build_tools(self) -> list[Callable[..., Any]]:
        def list_dir(relative_path: str = ".") -> list[str]:
            """List files under the task-local DeepAgent workspace."""
            return self.file_tools.list_dir(relative_path)

        def read_file(relative_path: str) -> str:
            """Read a UTF-8 file from the task-local DeepAgent workspace."""
            return self.file_tools.read_file(relative_path)

        def write_file(relative_path: str, content: str) -> dict[str, Any]:
            """Write a UTF-8 file under records/ or outputs/ in the run workspace."""
            return self.file_tools.write_file(relative_path, content)

        return [list_dir, read_file, write_file]

    def run(
        self,
        request: DeepAgentRunRequest,
        *,
        controller: CancellationController | None = None,
    ) -> DeepAgentRunResult:
        active_controller = controller or self.file_tools.controller
        active_controller.raise_if_cancelled()
        if self.agent_factory is None:
            raise DeepAgentUnavailableError("deepagents 运行库未安装，DeepAgent 适配器不可用。")

        agent = self.agent_factory(
            model=request.model,
            tools=self.build_tools(),
            system_prompt=deep_agent_system_prompt(),
            subagents=deep_agent_subagents(),
            backend=AuditedDeepAgentBackend(self.file_tools),
        )
        active_controller.raise_if_cancelled()
        result = self._invoke_agent(agent, request)
        active_controller.raise_if_cancelled()
        return DeepAgentRunResult(
            status="complete",
            output_text=self._output_text(result),
            metadata={"adapter": "deepagents", "result_type": type(result).__name__},
        )

    def _invoke_agent(self, agent: Any, request: DeepAgentRunRequest) -> Any:
        payload = {
            "messages": [{"role": "user", "content": request.message}],
        }
        config = {"configurable": {"thread_id": f"{request.task_id}:{request.run_id}"}}
        if hasattr(agent, "invoke"):
            try:
                return agent.invoke(payload, config=config)
            except TypeError:
                return agent.invoke(payload)
        if hasattr(agent, "run"):
            return agent.run(payload)
        if callable(agent):
            try:
                return agent(payload, config=config)
            except TypeError:
                return agent(payload)
        raise TypeError("DeepAgent factory 必须返回 callable、invoke 或 run 对象")

    @staticmethod
    def _output_text(result: Any) -> str:
        if isinstance(result, str):
            return result
        if isinstance(result, Mapping):
            for key in ("content", "output", "text", "response", "final"):
                value = result.get(key)
                if isinstance(value, str):
                    return value
            messages = result.get("messages")
            if isinstance(messages, list):
                for message in reversed(messages):
                    if not isinstance(message, Mapping):
                        continue
                    content = message.get("content")
                    if isinstance(content, str):
                        return content
        return "DeepAgent 运行完成。"


def deep_agent_system_prompt() -> str:
    return (
        "你是 MyAgent 的任务内 DeepAgent。只能使用提供的文件工具访问当前运行工作区；"
        "uploads/ 是本轮显式选择的只读上传快照，records/ 用于过程记录，outputs/ 用于"
        "需要交付给用户的结果文件。不要尝试访问绝对路径、密钥、系统目录或任务工作区外部文件。"
    )


def deep_agent_subagents() -> list[dict[str, Any]]:
    return [
        {
            "name": "file-record-agent",
            "description": (
                "在任务运行工作区内读取显式选择的上传快照，整理 records/ 过程记录，"
                "并将可交付结果写入 outputs/。"
            ),
            "system_prompt": (
                "你只处理当前 run workspace 中的文件。读取 uploads/，写入 records/ 或 outputs/。"
            ),
            "tools": [],
        }
    ]


def datetime_from_timestamp(timestamp: float) -> str:
    return (
        datetime.fromtimestamp(timestamp, timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
