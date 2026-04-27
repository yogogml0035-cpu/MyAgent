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
            return ActionDecision("allow", "Inside current task workspace")
        if any(self._is_within(resolved, grant) for grant in self._task_grants):
            return ActionDecision("allow", "Covered by task-local grant")
        if write:
            return ActionDecision(
                "confirm", "Write outside the task workspace requires confirmation"
            )
        return ActionDecision("confirm", "Read outside the task workspace requires confirmation")

    def classify_command(self, command: list[str] | str) -> ActionDecision:
        parts = shlex.split(command) if isinstance(command, str) else command
        if not parts:
            return ActionDecision("deny", "Empty command")
        normalized = tuple(parts)
        if normalized in ALLOWED_COMMANDS:
            return ActionDecision("allow", "Command is on the task-tool allowlist")
        return ActionDecision("deny", "Command is not on the task-tool allowlist")

    @staticmethod
    def _is_within(path: Path, root: Path) -> bool:
        return path == root or root in path.parents
