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
        raise ValueError(f"Path '{path}' is outside the workspace root")
    return resolved


def _make_fs_tools(workspace_root: Path) -> tuple:
    @tool
    def read_file(path: str) -> str:
        """Read the contents of a file inside the task workspace."""
        try:
            resolved = _validate_path(path, workspace_root)
        except ValueError as exc:
            return f"Error: {exc}"
        if not resolved.is_file():
            return f"Error: file not found: {path}"
        try:
            return resolved.read_text(encoding="utf-8")
        except Exception as exc:
            return f"Error reading file: {exc}"

    @tool
    def write_file(path: str, content: str) -> str:
        """Write *content* to a file inside the task workspace."""
        try:
            resolved = _validate_path(path, workspace_root)
        except ValueError as exc:
            return f"Error: {exc}"
        try:
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_text(content, encoding="utf-8")
            return f"OK: wrote {len(content)} characters to {path}"
        except Exception as exc:
            return f"Error writing file: {exc}"

    @tool
    def list_files(path: str = ".") -> str:
        """List files and directories under a path inside the task workspace."""
        try:
            resolved = _validate_path(path, workspace_root)
        except ValueError as exc:
            return f"Error: {exc}"
        if not resolved.is_dir():
            return f"Error: not a directory: {path}"
        entries = sorted(resolved.iterdir())
        if not entries:
            return "(empty directory)"
        lines: list[str] = []
        for entry in entries:
            suffix = "/" if entry.is_dir() else ""
            lines.append(f"{entry.name}{suffix}")
        return "\n".join(lines)

    return read_file, write_file, list_files
