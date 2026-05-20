#!/usr/bin/env python3
"""
Ralph Dashboard - 实时监控面板
启动一个本地 HTTP 服务，服务 dashboard.html 并提供 /api/state 接口。
"""

import json
import os
import platform
import shutil
import subprocess
import threading
import webbrowser
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
PRD_FILE = SCRIPT_DIR / "prd.json"
PROGRESS_FILE = SCRIPT_DIR / "progress.txt"
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
    current_story: str | None = None,
) -> None:
    with _state_lock:
        if iteration is not None:
            _state["iteration"] = iteration
        if phase is not None:
            _state["phase"] = phase
        if current_story is not None:
            _state["current_story"] = current_story


def _build_api_response() -> dict:
    with _state_lock:
        s = dict(_state)

    elapsed = int(time.time() - s["started_at"]) if s["started_at"] else 0

    project = ""
    branch_name = ""
    stories = []
    try:
        prd = json.loads(PRD_FILE.read_text(encoding="utf-8"))
        project = prd.get("project", "")
        branch_name = prd.get("branchName", "")
        stories = prd.get("userStories", [])
    except Exception:
        pass

    logs = ""
    try:
        if PROGRESS_FILE.exists():
            logs = PROGRESS_FILE.read_text(encoding="utf-8")
    except Exception:
        pass

    return {
        "runtime": {
            "iteration": s["iteration"],
            "max_iterations": s["max_iterations"],
            "phase": s["phase"],
            "current_story": s["current_story"],
            "elapsed": elapsed,
        },
        "project": project,
        "branchName": branch_name,
        "stories": stories,
        "logs": logs,
    }


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path = self.path.split("?")[0]

        if path == "/api/state":
            body = json.dumps(_build_api_response(), ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        elif path in ("/", "/index.html"):
            try:
                html = HTML_FILE.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
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


def start(port: int = 7331, max_iterations: int = 50, open_browser: bool = True) -> None:
    with _state_lock:
        _state["started_at"] = time.time()
        _state["max_iterations"] = max_iterations

    server = HTTPServer(("127.0.0.1", port), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    url = f"http://localhost:{port}"
    print(f"🖥️  Dashboard: {url}")

    if open_browser:
        threading.Timer(0.8, lambda: _open_browser(url)).start()
