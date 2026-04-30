from __future__ import annotations

import asyncio
import fnmatch
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .agent_activity import ActivitySink, DeepAgentActivityProjector
from .agent_profiles import (
    DEFAULT_FILE_AGENT_PROFILE,
    AgentProfile,
    compile_subagents_for_deepagents,
)
from .runtime import CancellationController
from .tools import (
    AuditedWorkspaceTools,
    AuditOperation,
    is_windows_absolute_path,
)

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
DEEPAGENT_VIRTUAL_ROOTS = ("uploads", "records", "outputs")
DEEP_AGENT_NO_FINAL_MESSAGE = "DeepAgent 未生成最终回答；已保留安全执行日志。"


class AuditedDeepAgentBackend(ImportedBackendProtocol):
    """DeepAgents backend protocol implementation backed by audited task tools."""

    def __init__(self, file_tools: AuditedWorkspaceTools) -> None:
        self.file_tools = file_tools
        self.virtual_mode = True
        self.audited = True

    def ls(self, path: str) -> LsResult:
        try:
            relative_path = self._relative_path_for_tool(path, "list_dir", "list")
            names = self.file_tools.list_dir(relative_path)
            entries = [
                self._file_info(self._join_relative(relative_path, name))
                for name in names
            ]
            return LsResult(entries=entries)
        except Exception as exc:
            return LsResult(error=self._safe_error(exc))

    async def als(self, path: str) -> LsResult:
        return await asyncio.to_thread(self.ls, path)

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:
        try:
            relative_path = self._relative_path_for_tool(file_path, "read_file", "read")
            content = self.file_tools.read_file(relative_path)
            selected = "\n".join(content.splitlines()[offset : offset + limit])
            return ReadResult(
                file_data={
                    "content": selected,
                    "encoding": "utf-8",
                }
            )
        except Exception as exc:
            return ReadResult(error=self._safe_error(exc))

    async def aread(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:
        return await asyncio.to_thread(self.read, file_path, offset, limit)

    def grep(
        self, pattern: str, path: str | None = None, glob: str | None = None
    ) -> GrepResult:
        relative_root: str | None = None
        try:
            relative_root = self._relative_path_for_tool(path or "/", "grep", "grep")
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
            if relative_root is not None:
                self.file_tools.audit_file_operation(
                    "grep", "grep", relative_root, "failed", str(exc)
                )
            return GrepResult(error=self._safe_error(exc))

    async def agrep(
        self, pattern: str, path: str | None = None, glob: str | None = None
    ) -> GrepResult:
        return await asyncio.to_thread(self.grep, pattern, path, glob)

    def glob(self, pattern: str, path: str = "/") -> GlobResult:
        relative_root: str | None = None
        try:
            relative_root = self._relative_path_for_tool(path, "glob", "glob")
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
            if relative_root is not None:
                self.file_tools.audit_file_operation(
                    "glob", "glob", relative_root, "failed", str(exc)
                )
            return GlobResult(error=self._safe_error(exc))

    async def aglob(self, pattern: str, path: str = "/") -> GlobResult:
        return await asyncio.to_thread(self.glob, pattern, path)

    def write(self, file_path: str, content: str) -> WriteResult:
        try:
            relative_path = self._relative_path_for_tool(file_path, "write_file", "write")
            path = self._workspace_path(relative_path)
            if path.exists():
                return WriteResult(error=f"文件已存在：{file_path}")
            result = self.file_tools.write_file(relative_path, content)
            return WriteResult(path=self._virtual_path(str(result["relative_path"])))
        except Exception as exc:
            return WriteResult(error=self._safe_error(exc))

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
            relative_path = self._relative_path_for_tool(file_path, "edit_file", "write")
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
            return EditResult(error=self._safe_error(exc))

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
        normalized = raw_path.strip().replace("\\", "/") or "/"
        if is_windows_absolute_path(normalized):
            raise PermissionError("路径超出任务工作区")
        if normalized in {"/", "."}:
            return "."
        if not normalized.startswith("/"):
            return normalized
        candidate = normalized.lstrip("/")
        first_segment = candidate.split("/", 1)[0]
        for prefix in DEEPAGENTS_INTERNAL_PREFIXES:
            if candidate == prefix or candidate.startswith(f"{prefix}/"):
                return f"records/deepagents/{candidate}"
        if first_segment in DEEPAGENT_VIRTUAL_ROOTS:
            return candidate
        raise PermissionError("路径超出任务工作区")

    def _relative_path_for_tool(
        self, raw_path: str, tool: str, operation: AuditOperation
    ) -> str:
        try:
            return self._relative_virtual_path(raw_path)
        except PermissionError as exc:
            self.file_tools.audit_file_operation(
                tool, operation, raw_path, "denied", str(exc)
            )
            raise

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

    def _safe_error(self, exc: Exception) -> str:
        return self.file_tools.sanitize_reason(exc)


class DeepAgentUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class DeepAgentRunRequest:
    task_id: str
    run_id: str
    message: str
    model: str
    agent_profile: AgentProfile = DEFAULT_FILE_AGENT_PROFILE


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
        activity_sink: ActivitySink | None = None,
    ) -> None:
        self.file_tools = file_tools
        self.agent_factory = agent_factory if agent_factory is not None else _DEFAULT_AGENT_FACTORY
        self.activity_sink = activity_sink

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

        tools = self.build_tools()
        tool_registry = {tool.__name__: tool for tool in tools}
        agent = self.agent_factory(
            model=request.model,
            tools=tools,
            system_prompt=deep_agent_system_prompt(request.agent_profile),
            subagents=compile_subagents_for_deepagents(request.agent_profile, tool_registry),
            backend=AuditedDeepAgentBackend(self.file_tools),
        )
        active_controller.raise_if_cancelled()
        projector = DeepAgentActivityProjector(
            task_id=request.task_id,
            run_id=request.run_id,
            sink=self.activity_sink,
        )
        projector.emit_started()
        try:
            output_text, result_type, execution_mode = self._run_agent(
                agent, request, active_controller, projector
            )
            active_controller.raise_if_cancelled()
            if output_text != DEEP_AGENT_NO_FINAL_MESSAGE:
                projector.record_final_output_text(output_text)
            projector.emit_completed()
            return DeepAgentRunResult(
                status="complete",
                output_text=output_text,
                metadata={
                    "adapter": "deepagents",
                    "result_type": result_type,
                    "execution_mode": execution_mode,
                    "chosen_profile_id": request.agent_profile.id,
                    "chosen_profile_label": request.agent_profile.label,
                    "strategy": request.agent_profile.strategy,
                    "planned_subagents": request.agent_profile.planned_subagents,
                },
            )
        except Exception:
            projector.emit_failed()
            raise

    def _run_agent(
        self,
        agent: Any,
        request: DeepAgentRunRequest,
        controller: CancellationController,
        projector: DeepAgentActivityProjector,
    ) -> tuple[str, str, str]:
        stream = getattr(agent, "stream", None)
        if callable(stream):
            stream_result = self._stream_agent(stream, request, controller, projector)
            if stream_result is not None:
                return stream_result
        projector.emit_invoke_fallback()
        result = self._invoke_agent(agent, request)
        return self._output_text(result), type(result).__name__, "invoke"

    def _stream_agent(
        self,
        stream: Callable[..., Any],
        request: DeepAgentRunRequest,
        controller: CancellationController,
        projector: DeepAgentActivityProjector,
    ) -> tuple[str, str, str] | None:
        payload = self._agent_payload(request)
        config = self._agent_config(request)
        try:
            chunks = stream(
                payload,
                config=config,
                subgraphs=True,
                version="v2",
                stream_mode=["updates", "messages"],
            )
        except TypeError:
            return None

        consumed_chunk = False
        try:
            for chunk in chunks:
                consumed_chunk = True
                controller.raise_if_cancelled()
                projector.observe_stream_chunk(chunk)
        except TypeError:
            if consumed_chunk:
                raise
            return None
        if projector.final_output_text:
            return projector.final_output_text, "stream", "stream"
        return DEEP_AGENT_NO_FINAL_MESSAGE, "stream_no_assistant_final", "stream"

    def _invoke_agent(self, agent: Any, request: DeepAgentRunRequest) -> Any:
        payload = self._agent_payload(request)
        config = self._agent_config(request)
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
    def _agent_payload(request: DeepAgentRunRequest) -> dict[str, Any]:
        return {
            "messages": [{"role": "user", "content": request.message}],
        }

    @staticmethod
    def _agent_config(request: DeepAgentRunRequest) -> dict[str, Any]:
        return {"configurable": {"thread_id": f"{request.task_id}:{request.run_id}"}}

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
                    role = str(message.get("role") or message.get("type") or "").lower()
                    if role and role not in {"assistant", "ai", "ai_message"}:
                        continue
                    content = message.get("content")
                    if isinstance(content, str):
                        return content
        return DEEP_AGENT_NO_FINAL_MESSAGE


def deep_agent_system_prompt(profile: AgentProfile = DEFAULT_FILE_AGENT_PROFILE) -> str:
    return (
        "你是 MyAgent 的任务内 DeepAgent。只能使用提供的文件工具访问当前运行工作区；"
        "uploads/ 是本轮可用的只读上传快照，不是默认必须读取的内容；是否列出、检索或读取"
        "这些文件由你根据用户任务自主决定。普通闲聊或无需文件依据的问题可以不读取 uploads/。"
        "records/ 用于过程记录，outputs/ 用于需要交付给用户的结果文件。复杂文件任务应先在"
        "records/ 写入简短 task-plan/todo，再按需要调用子 Agent；只有当多文档、多投标人、"
        "多维度并行检查或报告生成与证据归一化可以隔离推进时才使用子 Agent。工具结果只是"
        "过程依据，必须在最后综合成面向用户的最终回答。若生成可交付文件，写入 outputs/。"
        f"当前已选择 Agent Profile：{profile.label}（{profile.id}）。{profile.system_prompt_fragment}"
        "围串标/投标比对任务优先输出 outputs/report.html、outputs/final-summary.md、"
        "outputs/evidence.json 和 outputs/task-plan.md，其中 evidence.json 使用规范字段："
        "category、severity、title、description、bidders、pair、locations、"
        "requirement_reference、confidence、source_agent、rationale_summary。不要尝试访问绝对路径、"
        "密钥、系统目录或任务工作区外部文件。不要在最终回答或输出文件中泄露隐藏推理、原始提示、"
        "密钥、授权头或不必要的上传原文。"
    )


def deep_agent_subagents(tool_registry: dict[str, Callable[..., Any]]) -> list[dict[str, Any]]:
    return compile_subagents_for_deepagents(DEFAULT_FILE_AGENT_PROFILE, tool_registry)


def datetime_from_timestamp(timestamp: float) -> str:
    return (
        datetime.fromtimestamp(timestamp, timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
