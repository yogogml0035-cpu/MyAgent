"""Bridge between local task storage and DeepAgents FilesystemMiddleware.

Provides LangChain ``@tool`` functions for reading, writing, and listing files
within a task workspace.  All paths are validated against the workspace root to
prevent directory-traversal escapes.
"""

from __future__ import annotations

from pathlib import Path

from langchain_core.tools import tool


def _validate_path(path: str, workspace_root: Path) -> Path:
    """Resolve *path* and ensure it stays within *workspace_root*.

    Raises ``ValueError`` if the resolved path escapes the workspace.
    """
    resolved = (workspace_root / path).resolve()
    root = workspace_root.resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError(f"路径“{path}”超出工作区根目录")
    return resolved


def _make_fs_tools(workspace_root: Path) -> tuple:
    @tool
    def read_file(path: str) -> str:
        """读取任务工作区内文件的内容。"""
        try:
            resolved = _validate_path(path, workspace_root)
        except ValueError as exc:
            return f"错误：{exc}"
        if not resolved.is_file():
            return f"错误：未找到文件：{path}"
        try:
            return resolved.read_text(encoding="utf-8")
        except Exception as exc:
            return f"读取文件失败：{exc}"

    @tool
    def write_file(path: str, content: str) -> str:
        """将内容写入任务工作区内的文件。"""
        try:
            resolved = _validate_path(path, workspace_root)
        except ValueError as exc:
            return f"错误：{exc}"
        try:
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_text(content, encoding="utf-8")
            return f"已将 {len(content)} 个字符写入 {path}"
        except Exception as exc:
            return f"写入文件失败：{exc}"

    @tool
    def list_files(path: str = ".") -> str:
        """列出任务工作区内指定路径下的文件和目录。"""
        try:
            resolved = _validate_path(path, workspace_root)
        except ValueError as exc:
            return f"错误：{exc}"
        if not resolved.is_dir():
            return f"错误：不是目录：{path}"
        entries = sorted(resolved.iterdir())
        if not entries:
            return "（空目录）"
        lines: list[str] = []
        for entry in entries:
            suffix = "/" if entry.is_dir() else ""
            lines.append(f"{entry.name}{suffix}")
        return "\n".join(lines)

    return read_file, write_file, list_files
