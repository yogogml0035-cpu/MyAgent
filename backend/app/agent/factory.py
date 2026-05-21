"""Agent factory wrapping create_deep_agent() with platform defaults."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from langgraph.graph.state import CompiledStateGraph

from app.agent.middleware import build_full_middleware
from app.config import Settings

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.tools.base import BaseTool

logger = logging.getLogger(__name__)

try:
    from deepagents import create_deep_agent
    from deepagents.backends import (
        BackendProtocol,
        CompositeBackend,
        FilesystemBackend,
        StateBackend,
        StoreBackend,
    )
    from deepagents.backends.protocol import (
        EditResult,
        FileDownloadResponse,
        FileUploadResponse,
        GlobResult,
        GrepResult,
        LsResult,
        ReadResult,
        WriteResult,
    )
except ImportError as exc:
    raise ImportError(
        "deepagents is not installed. "
        "Install it with: uv add deepagents"
    ) from exc


_SKILLS_ROUTE = "/skills/"


class _ReadOnlyBackend(BackendProtocol):
    """Expose configured skill files without allowing agent writes."""

    def __init__(self, backend: BackendProtocol) -> None:
        self._backend = backend

    def ls(self, path: str) -> LsResult:
        return self._backend.ls(path)

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:
        return self._backend.read(file_path, offset=offset, limit=limit)

    def grep(self, pattern: str, path: str | None = None, glob: str | None = None) -> GrepResult:
        return self._backend.grep(pattern, path=path, glob=glob)

    def glob(self, pattern: str, path: str = "/") -> GlobResult:
        return self._backend.glob(pattern, path=path)

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        return self._backend.download_files(paths)

    def write(self, file_path: str, content: str) -> WriteResult:
        return WriteResult(error=f"Cannot write to read-only skills path: {file_path}")

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        return EditResult(error=f"Cannot edit read-only skills path: {file_path}")

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        return [
            FileUploadResponse(path=path, error="permission_denied")
            for path, _content in files
        ]


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _resolve_skill_source(source: str) -> Path:
    path = Path(source)
    if path.is_absolute():
        return path.resolve()
    return (_backend_root() / path).resolve()


def _mount_skill_sources(
    routes: dict[str, BackendProtocol],
    skills: list[str] | None,
) -> list[str] | None:
    if skills is None:
        return None

    mounted_sources: list[str] = []
    single_source = len(skills) == 1
    for index, source in enumerate(skills):
        source_path = _resolve_skill_source(source)
        route = _SKILLS_ROUTE if single_source else f"/skills/source-{index}/"
        routes[route] = _ReadOnlyBackend(
            FilesystemBackend(root_dir=source_path, virtual_mode=True)
        )
        mounted_sources.append(route)

    return mounted_sources


def _make_backend(
    workspace_dir: Path | None,
    *,
    store=None,
    skills: list[str] | None = None,
) -> tuple[CompositeBackend, list[str] | None]:
    root = workspace_dir.resolve() if workspace_dir else Path.cwd()
    logger.debug("Creating CompositeBackend with workspace root_dir=%s", root)
    routes: dict[str, BackendProtocol] = {"/scratch/": StateBackend()}
    if store is not None:
        routes["/memories/"] = StoreBackend(store=store)
    mounted_skills = _mount_skill_sources(routes, skills)
    return CompositeBackend(
        default=FilesystemBackend(root_dir=root, virtual_mode=True),
        routes=routes,
    ), mounted_skills


def build_agent(
    settings: Settings,
    *,
    model: str | None = None,
    tools: Sequence[BaseTool | Callable | dict] | None = None,
    system_prompt: str | None = None,
    skills: list[str] | None = None,
    subagents: Sequence | None = None,
    workspace_dir: Path | None = None,
    checkpointer=None,
    store=None,
) -> CompiledStateGraph:
    model_id = model or settings.default_model
    chat_model = _create_model(model_id, settings)
    backend, mounted_skills = _make_backend(workspace_dir, store=store, skills=skills)

    return create_deep_agent(
        model=chat_model,
        tools=tools or [],
        system_prompt=system_prompt,
        skills=mounted_skills,
        subagents=subagents,
        backend=backend,
        checkpointer=checkpointer,
        store=store,
    )


def build_agent_with_middleware(
    settings: Settings,
    *,
    model: str | None = None,
    tools: Sequence[BaseTool | Callable | dict] | None = None,
    system_prompt: str | None = None,
    skills: list[str] | None = None,
    subagents: Sequence | None = None,
    workspace_dir: Path | None = None,
    checkpointer=None,
    store=None,
) -> CompiledStateGraph:
    model_id = model or settings.default_model
    chat_model = _create_model(model_id, settings)
    backend, mounted_skills = _make_backend(workspace_dir, store=store, skills=skills)

    extra_middleware = _build_extra_middleware(
        settings,
        model=chat_model,
        skills_sources=mounted_skills,
        subagents=subagents,
    )

    return create_deep_agent(
        model=chat_model,
        tools=tools or [],
        system_prompt=system_prompt,
        middleware=extra_middleware,
        skills=mounted_skills,
        subagents=subagents,
        backend=backend,
        checkpointer=checkpointer,
        store=store,
    )


def _build_extra_middleware(
    settings: Settings,
    *,
    model,
    skills_sources: list[str] | None = None,
    subagents: Sequence | None = None,
) -> list:
    return build_full_middleware(
        settings,
        model=model,
        skills_sources=skills_sources,
        subagents=list(subagents) if subagents is not None else None,
    )


def _create_model(model_id: str, settings: Settings) -> BaseChatModel:
    try:
        from app.models.provider import create_model
    except ImportError as exc:
        raise ImportError(
            "app.models.provider is not available. "
            "Ensure the model layer is implemented before building agents."
        ) from exc

    return create_model(model_id, settings=settings)
