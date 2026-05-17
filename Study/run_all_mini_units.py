from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def run(command: list[str], cwd: Path) -> None:
    print("$", " ".join(command))
    subprocess.run(command, cwd=cwd, check=True)


def main() -> None:
    python_units = sorted(ROOT.glob("chapters/*/mini_unit.py"))
    js_units = sorted(ROOT.glob("chapters/*/mini_unit.mjs"))

    for path in python_units:
        python = sys.executable or shutil.which("python3")
        if not python:
            raise RuntimeError("python3 not found")
        run([python, str(path)], ROOT.parent)

    node = shutil.which("node")
    if not node:
        print("node not found; skipped .mjs learning units")
        return

    for path in js_units:
        run([node, str(path)], ROOT.parent)


if __name__ == "__main__":
    main()
