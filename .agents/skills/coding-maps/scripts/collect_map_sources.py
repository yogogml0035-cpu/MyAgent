#!/usr/bin/env python3
"""发现生成仓库级 coding map 可能需要读取的源文件。"""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT_DOC_NAMES = (
    "AGENTS.md",
    "ARCHITECTURE.md",
    "INTERFACES.md",
    "DESIGN.md",
    "README.md",
)

CODEBASE_DOC_NAMES = (
    "ARCHITECTURE.md",
    "INTEGRATIONS.md",
    "STRUCTURE.md",
    "TESTING.md",
    "CONVENTIONS.md",
    "CONCERNS.md",
    "STACK.md",
    "README.md",
)

SKIP_DIRS = {
    ".git",
    ".agents",
    ".venv",
    ".next",
    ".pytest_cache",
    ".playwright-mcp",
    "node_modules",
    "__pycache__",
}


def rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def existing(paths: list[Path], root: Path) -> list[str]:
    return [rel(path, root) for path in paths if path.is_file()]


def iter_codebase_dirs(root: Path) -> list[Path]:
    found: list[Path] = []
    for path in root.rglob(".planning/codebase"):
        if not path.is_dir():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        found.append(path)
    return sorted(found, key=lambda item: rel(item, root))


def main() -> int:
    repo_root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    if not repo_root.is_dir():
        print(f"未找到仓库根目录: {repo_root}", file=sys.stderr)
        return 2

    root_docs = existing([repo_root / name for name in ROOT_DOC_NAMES], repo_root)

    subprojects = []
    for codebase_dir in iter_codebase_dirs(repo_root):
        docs = existing([codebase_dir / name for name in CODEBASE_DOC_NAMES], repo_root)
        subproject_root = codebase_dir.parent.parent
        subprojects.append(
            {
                "name": rel(subproject_root, repo_root),
                "codebase_dir": rel(codebase_dir, repo_root),
                "docs": docs,
            }
        )

    asset_docs = []
    asset_dir = repo_root / "asset"
    if asset_dir.is_dir():
        asset_docs = [rel(path, repo_root) for path in sorted(asset_dir.glob("*.md"))]

    output_dir = repo_root / "coding_maps"
    payload = {
        "repo_root": str(repo_root),
        "output_dir": rel(output_dir, repo_root),
        "output_file": rel(output_dir / "SYSTEM_MAP.md", repo_root),
        "existing_maps": existing([output_dir / "SYSTEM_MAP.md"], repo_root),
        "root_docs": root_docs,
        "subprojects": subprojects,
        "asset_docs": asset_docs,
        "warnings": [],
    }

    if not subprojects:
        payload["warnings"].append("未发现 .planning/codebase 目录。")
    if "AGENTS.md" not in root_docs:
        payload["warnings"].append("未发现根级 AGENTS.md。")

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
