from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from .permissions import PermissionPolicy
from .runtime import CancellationController, run_cancellable_command


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
            raise ValueError("write_markdown only writes .md files")
        decision = self.policy.classify_path_access(path, write=True)
        if decision.status != "allow":
            raise PermissionError(decision.reason)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def write_python_script(self, relative_path: str, content: str) -> Path:
        path = self._resolve(relative_path)
        if path.suffix.lower() != ".py":
            raise ValueError("write_python_script only writes .py files")
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
            return {"results": [], "warning": "TAVILY_API_KEY is not configured"}
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
            raise PermissionError("Path escapes the task workspace")
        return path
