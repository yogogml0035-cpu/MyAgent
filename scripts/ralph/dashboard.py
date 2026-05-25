#!/usr/bin/env python3
"""
Ralph Dashboard - 实时监控面板
启动一个本地 HTTP 服务，服务 dashboard.html 并提供 /api/state 接口。
"""

import json
import os
import platform
import re
import shutil
import subprocess
import threading
import webbrowser
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
PRD_FILE: Path | None = None
PROGRESS_FILE: Path | None = None
HTML_FILE = SCRIPT_DIR / "dashboard.html"
PIXEL_HTML_FILE = SCRIPT_DIR / "dashboard-p.html"

_state: dict = {
    "iteration": 0,
    "max_iterations": 50,
    "phase": "idle",       # idle | developing | validating | done | error
    "current_story": None,
    "started_at": None,
}
_state_lock = threading.Lock()
_UNSET = object()

ANSI_RE = re.compile(
    r"(?:"
    r"\x1b\][^\x07]*(?:\x07|\x1b\\)"
    r"|\x1b[P_X^_].*?\x1b\\"
    r"|\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])"
    r"|\x9b[0-?]*[ -/]*[@-~]"
    r"|\^\[(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])"
    r")",
    re.DOTALL,
)
STORY_ID_RE = re.compile(r"\bUS-\d+\b", re.IGNORECASE)
LOG_FILE_RE = re.compile(
    r"^(developer|validator)(?:[-_ ]?iteration[-_ ]?(\d+)|[-_ ]?(\d+))?\.log$",
    re.IGNORECASE,
)


def _is_wsl() -> bool:
    """当前 Python 是否运行在 WSL 中。"""
    if os.name != "posix" or platform.system() != "Linux":
        return False
    release = platform.release().lower()
    if "microsoft" in release or "wsl" in release:
        return True
    try:
        return "microsoft" in Path("/proc/version").read_text(encoding="utf-8").lower()
    except Exception:
        return False


def _open_browser(url: str) -> bool:
    """打开 Dashboard，WSL 下优先调用 Windows 侧浏览器。"""
    if _is_wsl():
        wslview = shutil.which("wslview")
        if wslview:
            subprocess.Popen([wslview, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True

        cmd = shutil.which("cmd.exe")
        if cmd:
            subprocess.Popen([cmd, "/c", "start", "", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True

        powershell = shutil.which("powershell.exe")
        if powershell:
            subprocess.Popen(
                [powershell, "-NoProfile", "-Command", "Start-Process", url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True

        print("⚠️  WSL 中未找到 wslview/cmd.exe/powershell.exe，请手动打开 Dashboard URL。")
        return False

    return webbrowser.open(url)


def set_state(
    iteration: int | None = None,
    phase: str | None = None,
    current_story: str | None | object = _UNSET,
) -> None:
    with _state_lock:
        if iteration is not None:
            _state["iteration"] = iteration
        if phase is not None:
            _state["phase"] = phase
        if current_story is not _UNSET:
            _state["current_story"] = current_story


def clean_terminal_text(text: str) -> str:
    text = ANSI_RE.sub("", text).replace("\r\n", "\n")
    lines = []
    for line in text.split("\n"):
        lines.append(line.split("\r")[-1])
    return "\n".join(lines)


def _clean_log_text(text: str) -> str:
    return clean_terminal_text(text)


def _relative_path(path: Path, base: Path) -> str:
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.name


def _read_log_slot(kind: str, path: Path, requirement_dir: Path) -> dict:
    label = "Developer" if kind == "developer" else "Validator"
    rel = _relative_path(path, requirement_dir)
    if not path.exists():
        return {
            "status": "missing",
            "path": rel,
            "content": "",
            "note": f"{label} log not found: {rel}",
        }

    try:
        content = _clean_log_text(path.read_text(encoding="utf-8", errors="replace"))
    except Exception as exc:
        return {
            "status": "error",
            "path": rel,
            "content": "",
            "note": f"Failed to read {label} log: {exc}",
        }

    return {
        "status": "ok" if content.strip() else "empty",
        "path": rel,
        "content": content,
        "note": "" if content.strip() else f"{label} log is empty: {rel}",
    }


def _missing_log_slot(story_id: str, kind: str, iteration_label: str) -> dict:
    label = "Developer" if kind == "developer" else "Validator"
    filename = f"{kind}.log" if iteration_label == "latest" else f"{kind}-iteration-{iteration_label}.log"
    rel = f"logs/{story_id}/{filename}"
    return {
        "status": "missing",
        "path": rel,
        "content": "",
        "note": f"{label} log not found: {rel}",
    }


def _parse_log_filename(name: str) -> tuple[str, int | None] | None:
    match = LOG_FILE_RE.fullmatch(name)
    if not match:
        return None
    iteration_text = match.group(2) or match.group(3)
    return match.group(1).lower(), int(iteration_text) if iteration_text else None


def _round_label(iteration: int | None) -> str:
    return f"{iteration:03d}" if iteration is not None else "latest"


def _scan_story_logs() -> dict[str, list[dict]]:
    if PROGRESS_FILE is None:
        return {}

    requirement_dir = PROGRESS_FILE.parent
    logs_dir = requirement_dir / "logs"
    if not logs_dir.exists():
        return {}

    by_story_iteration: dict[tuple[str, str], dict] = {}

    def add_log(path: Path, story_id: str, kind: str, iteration: int | None) -> None:
        iteration_label = _round_label(iteration)
        key = (story_id.upper(), iteration_label)
        round_entry = by_story_iteration.setdefault(
            key,
            {
                "storyId": story_id.upper(),
                "iteration": iteration,
                "iterationLabel": iteration_label,
                "heading": (
                    f"{story_id.upper()} iteration {iteration_label}"
                    if iteration is not None
                    else f"{story_id.upper()} latest logs"
                ),
            },
        )
        round_entry[kind] = _read_log_slot(kind, path, requirement_dir)

    for story_dir in logs_dir.iterdir():
        if not story_dir.is_dir():
            continue
        story_match = STORY_ID_RE.fullmatch(story_dir.name)
        if not story_match:
            continue

        story_id = story_match.group(0).upper()
        for path in story_dir.iterdir():
            if not path.is_file():
                continue
            parsed_log = _parse_log_filename(path.name)
            if not parsed_log:
                continue
            kind, iteration = parsed_log
            add_log(path, story_id, kind, iteration)

    # Backward compatibility: old flat log names can still appear in historical task dirs.
    for path in logs_dir.iterdir():
        if not path.is_file():
            continue
        parsed_log = _parse_log_filename(path.name)
        if not parsed_log:
            continue
        story_match = STORY_ID_RE.search(path.read_text(encoding="utf-8", errors="replace"))
        if story_match:
            kind, iteration = parsed_log
            add_log(path, story_match.group(0).upper(), kind, iteration)

    story_logs: dict[str, list[dict]] = {}
    for (story_id, iteration_label), round_entry in by_story_iteration.items():
        round_entry.setdefault("developer", _missing_log_slot(story_id, "developer", iteration_label))
        round_entry.setdefault("validator", _missing_log_slot(story_id, "validator", iteration_label))
        story_logs.setdefault(story_id, []).append(round_entry)

    for rounds in story_logs.values():
        rounds.sort(key=lambda item: (item["iteration"] is None, item["iteration"] or 0))

    return story_logs


def _build_api_response() -> dict:
    with _state_lock:
        s = dict(_state)

    elapsed = int(time.time() - s["started_at"]) if s["started_at"] else 0
    phase = s["phase"]
    current_story = s["current_story"] if phase in ("developing", "validating") else None

    project = ""
    branch_name = ""
    stories = []
    try:
        if PRD_FILE is not None:
            prd = json.loads(PRD_FILE.read_text(encoding="utf-8"))
            project = prd.get("project", "")
            branch_name = prd.get("branchName", "")
            stories = prd.get("userStories", [])
    except Exception:
        pass

    logs = ""
    try:
        if PROGRESS_FILE is not None and PROGRESS_FILE.exists():
            logs = _clean_log_text(PROGRESS_FILE.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        pass
    story_logs = _scan_story_logs()

    return {
        "runtime": {
            "iteration": s["iteration"],
            "max_iterations": s["max_iterations"],
            "phase": phase,
            "current_story": current_story,
            "elapsed": elapsed,
        },
        "project": project,
        "branchName": branch_name,
        "stories": stories,
        "logs": logs,
        "storyLogs": story_logs,
    }


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path = self.path.split("?")[0]

        if path == "/api/state":
            body = json.dumps(_build_api_response(), ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-store, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        elif path in ("/", "/index.html"):
            try:
                html = HTML_FILE.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store, max-age=0")
                self.send_header("Content-Length", str(len(html)))
                self.end_headers()
                self.wfile.write(html)
            except Exception as e:
                msg = str(e).encode()
                self.send_response(500)
                self.send_header("Content-Length", str(len(msg)))
                self.end_headers()
                self.wfile.write(msg)

        elif path in ("/p", "/p.html"):
            try:
                html = PIXEL_HTML_FILE.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store, max-age=0")
                self.send_header("Content-Length", str(len(html)))
                self.end_headers()
                self.wfile.write(html)
            except Exception as e:
                msg = str(e).encode()
                self.send_response(500)
                self.send_header("Content-Length", str(len(msg)))
                self.end_headers()
                self.wfile.write(msg)

        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format: str, *args) -> None:  # suppress access logs
        pass


def start(
    port: int = 7331,
    max_iterations: int = 50,
    open_browser: bool = True,
    prd_file: Path | None = None,
    progress_file: Path | None = None,
) -> None:
    global PRD_FILE, PROGRESS_FILE

    if prd_file is not None:
        PRD_FILE = Path(prd_file)
    if progress_file is not None:
        PROGRESS_FILE = Path(progress_file)

    with _state_lock:
        _state["started_at"] = time.time()
        _state["max_iterations"] = max_iterations

    server = None
    actual_port = port
    for candidate in range(port, port + 100):
        try:
            server = HTTPServer(("127.0.0.1", candidate), _Handler)
            actual_port = candidate
            break
        except OSError:
            continue

    if server is None:
        raise RuntimeError(f"No available dashboard port found from {port} to {port + 99}")

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    url = f"http://localhost:{actual_port}"
    print(f"🖥️  Dashboard: {url}")

    if open_browser:
        threading.Timer(0.8, lambda: _open_browser(url)).start()
