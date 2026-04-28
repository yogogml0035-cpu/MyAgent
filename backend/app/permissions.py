from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import Path

ALLOWED_COMMANDS = {
    ("pytest",),
    ("pytest", "-q"),
    ("uv", "run", "pytest"),
    ("uv", "run", "pytest", "-q"),
}


@dataclass(frozen=True)
class ActionDecision:
    status: str
    reason: str


class PermissionPolicy:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root.resolve()
        self._task_grants: set[Path] = set()

    def grant_for_task(self, path: Path) -> None:
        self._task_grants.add(path.resolve())

    def classify_path_access(self, target: Path, *, write: bool = False) -> ActionDecision:
        resolved = target.resolve()
        if self._is_within(resolved, self.workspace_root):
            return ActionDecision("allow", "位于当前任务工作区内")
        if any(self._is_within(resolved, grant) for grant in self._task_grants):
            return ActionDecision("allow", "已被任务本地授权覆盖")
        if write:
            return ActionDecision(
                "confirm", "写入任务工作区外部需要确认"
            )
        return ActionDecision("confirm", "读取任务工作区外部需要确认")

    def classify_command(self, command: list[str] | str) -> ActionDecision:
        parts = shlex.split(command) if isinstance(command, str) else command
        if not parts:
            return ActionDecision("deny", "命令为空")
        normalized = tuple(parts)
        if normalized in ALLOWED_COMMANDS:
            return ActionDecision("allow", "命令在任务工具允许列表中")
        return ActionDecision("deny", "命令不在任务工具允许列表中")

    @staticmethod
    def _is_within(path: Path, root: Path) -> bool:
        return path == root or root in path.parents
