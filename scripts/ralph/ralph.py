#!/usr/bin/env python3
"""
Ralph - 自主 AI Agent 循环执行器（含 Validator）
"""

import json
import argparse
import sys
import subprocess
import time
import os
import platform
import signal
import shlex
import shutil
import socket
import queue
import threading
from pathlib import Path
from datetime import datetime

import dashboard

# 配置
MAX_ITERATIONS = 200
TIMEOUT_SECONDS = 30 * 60
CODEX_COMPLETION_IDLE_SECONDS = 20
CODEX_COMPLETION_MAX_EXIT_SECONDS = 120
CODEX_ARTIFACT_COMPLETION_IDLE_SECONDS = 60

def is_windows() -> bool:
    """当前 Python 是否运行在原生 Windows 上。"""
    return os.name == "nt"


def is_macos() -> bool:
    """当前 Python 是否运行在 macOS 上。"""
    return platform.system() == "Darwin"


def configure_utf8_stdio() -> None:
    """降低 Windows/PowerShell 默认编码导致的中文输出乱码或编码异常。"""
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass


def resolve_executable(name: str) -> str:
    """
    在 Windows 上，很多 CLI 会以 .cmd/.bat 形式存在（例如 npm 全局安装的命令）。
    这里做一层兼容解析，避免 WinError 2。
    """
    path = shutil.which(name)
    if path:
        return path

    if is_windows():
        for ext in (".cmd", ".exe", ".bat"):
            path = shutil.which(name + ext)
            if path:
                return path

    # 让上层捕获并打印更明确的错误信息
    raise FileNotFoundError(
        f"找不到可执行文件: {name}（请确认已安装且在 PATH 中，Windows 可能是 {name}.cmd）"
    )


def build_cmd(prompt: str) -> list[str]:
    """根据 AGENT 配置构建命令"""
    if AGENT == "codex":
        codex = resolve_executable("codex")
        return [
            codex,
            "exec",
            "--color",
            "never",
            "--dangerously-bypass-approvals-and-sandbox",
            "-",
        ]
    claude = resolve_executable("claude")
    return [claude, "--print", "--dangerously-skip-permissions", prompt]


def build_process_cmd(prompt: str) -> list[str]:
    """构建子进程命令，必要时通过 script 提供 PTY。"""
    if AGENT == "codex":
        return build_cmd(prompt)

    # Windows 没有 script(1)，直接运行子命令即可
    if is_windows():
        return build_cmd(prompt)

    cmd = build_cmd(prompt)
    script = shutil.which("script")
    if not script:
        print("⚠️  未找到 script(1)，将直接运行 Agent；如果 Agent 要求 TTY，可能会失败。")
        return cmd

    # macOS/BSD script 支持：script -q /dev/null command args...
    if is_macos():
        return [script, "-q", "/dev/null"] + cmd

    # Linux/WSL 的 util-linux script 不支持把 command args 直接追加在文件名后；
    # 必须使用 -c，否则 Codex/Claude 的参数会被 script 当成自己的参数解析。
    return [script, "-q", "-e", "-c", shlex.join(cmd), "/dev/null"]


def prompt_stdin(prompt: str) -> str | None:
    """Codex reads '-' from stdin so Windows .cmd wrappers cannot truncate multiline prompts."""
    if AGENT == "codex":
        return prompt
    return None


def start_agent_process(cmd: list[str], prompt: str) -> subprocess.Popen:
    stdin_prompt = prompt_stdin(prompt)
    process = subprocess.Popen(
        cmd,
        cwd=str(PROJECT_ROOT),
        env=child_process_env(),
        stdin=subprocess.PIPE if stdin_prompt is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        start_new_session=not is_windows(),
    )
    if stdin_prompt is not None and process.stdin is not None:
        try:
            process.stdin.write(stdin_prompt)
            process.stdin.close()
        except (BrokenPipeError, OSError):
            pass
    return process


def stop_process(process: subprocess.Popen | None) -> None:
    """跨平台停止 Ralph 启动的后台进程。"""
    if process is None or process.poll() is not None:
        return

    try:
        if is_windows():
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            return

        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            process.wait()
    except Exception:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def child_process_env() -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
        }
    )
    if not is_windows():
        env.setdefault("LANG", "C.UTF-8")
        env.setdefault("LC_ALL", "C.UTF-8")
    if AGENT == "codex":
        env.update(
            {
                "TERM": "dumb",
                "NO_COLOR": "1",
                "CLICOLOR": "0",
                "CLICOLOR_FORCE": "0",
                "FORCE_COLOR": "0",
            }
        )
    return env

# 目录配置
SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = SCRIPT_DIR.parent.parent
CLAUDE_INSTRUCTION_FILE = SCRIPT_DIR / "CLAUDE.md"
VALIDATOR_INSTRUCTION_FILE = SCRIPT_DIR / "VALIDATOR.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ralph autonomous runner for a task-scoped prd.json"
    )
    parser.add_argument(
        "--agent",
        choices=("claude", "codex"),
        default="claude",
        help="Agent runtime to use.",
    )
    parser.add_argument(
        "--prd-json",
        required=True,
        help="Explicit path to tasks/<requirement-slug>/prd.json.",
    )
    parser.add_argument(
        "--dashboard-port",
        type=int,
        default=7331,
        help="Preferred dashboard port. If occupied, the next available port is used.",
    )
    args = parser.parse_args()

    prd_path = Path(args.prd_json)
    if not prd_path.is_absolute():
        prd_path = PROJECT_ROOT / prd_path
    prd_path = prd_path.resolve()

    tasks_dir = (PROJECT_ROOT / "tasks").resolve()
    if prd_path.name != "prd.json" or prd_path.parent.parent.resolve() != tasks_dir:
        parser.error("--prd-json must point to tasks/<requirement-slug>/prd.json")
    if not prd_path.exists():
        parser.error(f"--prd-json does not exist: {prd_path}")

    args.prd_json = prd_path
    return args


configure_utf8_stdio()
ARGS = parse_args()
AGENT = ARGS.agent
PRD_FILE = ARGS.prd_json
REQUIREMENT_DIR = PRD_FILE.parent
REQUIREMENT_REL = REQUIREMENT_DIR.relative_to(PROJECT_ROOT)
PROGRESS_FILE = REQUIREMENT_DIR / "progress.txt"
SCREENSHOTS_DIR = REQUIREMENT_DIR / "screenshots"
LOGS_DIR = REQUIREMENT_DIR / "logs"


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def runtime_header() -> str:
    return (
        "# Ralph Progress\n\n"
        f"Requirement: {REQUIREMENT_REL.as_posix()}\n"
        f"Started: {now_text()}\n"
        "Source: prd.json\n\n"
        "## Codebase Patterns\n"
    )


def ensure_runtime_artifacts() -> None:
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    if not PROGRESS_FILE.exists() or PROGRESS_FILE.stat().st_size == 0:
        PROGRESS_FILE.write_text(runtime_header(), encoding="utf-8")


def requirement_path(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


def story_log_path(story_id: str | None, kind: str, iteration: int) -> Path:
    story_dir = story_id.upper() if story_id else "unassigned"
    return LOGS_DIR / story_dir / f"{kind}-iteration-{iteration:03d}.log"


def write_log(log_file: Path, message: str) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("a", encoding="utf-8") as f:
        f.write(f"[{now_text()}] {dashboard.clean_terminal_text(message)}\n")


def is_port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.4):
            return True
    except OSError:
        return False


def find_reusable_frontend_port() -> int | None:
    for port in (3000, 5173, 5174, 8080):
        if is_port_open(port):
            return port
    return None


def stream_process(
    process: subprocess.Popen,
    log_file: Path,
    timeout_seconds: int,
    timeout_label: str,
    completion_check=None,
) -> bool:
    start_time = time.time()
    last_output_time = start_time
    timed_out = False
    saw_codex_completion_marker = False
    codex_completion_seen_at: float | None = None
    output_queue: queue.Queue[str] = queue.Queue()

    def read_stdout() -> None:
        if process.stdout is None:
            return
        for line in process.stdout:
            output_queue.put(line)

    reader = threading.Thread(target=read_stdout, daemon=True)
    reader.start()

    with log_file.open("a", encoding="utf-8") as f:
        while True:
            while True:
                try:
                    line = output_queue.get_nowait()
                    clean_line = dashboard.clean_terminal_text(line)
                    last_output_time = time.time()
                    if "tokens used" in clean_line.lower():
                        saw_codex_completion_marker = True
                        if codex_completion_seen_at is None:
                            codex_completion_seen_at = last_output_time
                    print(clean_line, end="")
                    f.write(clean_line)
                    f.flush()
                except queue.Empty:
                    break

            ret_code = process.poll()
            if ret_code is not None:
                reader.join(timeout=1)
                while True:
                    try:
                        line = output_queue.get_nowait()
                        clean_line = dashboard.clean_terminal_text(line)
                        last_output_time = time.time()
                        print(clean_line, end="")
                        f.write(clean_line)
                    except queue.Empty:
                        break
                f.flush()
                break

            elapsed_time = time.time() - start_time
            idle_time = time.time() - last_output_time
            completion_marker_age = (
                time.time() - codex_completion_seen_at
                if codex_completion_seen_at is not None
                else 0
            )
            completed_by_artifacts = False
            if AGENT == "codex" and completion_check is not None:
                try:
                    completed_by_artifacts = bool(completion_check())
                except Exception:
                    completed_by_artifacts = False

            if (
                AGENT == "codex"
                and saw_codex_completion_marker
                and (
                    idle_time > CODEX_COMPLETION_IDLE_SECONDS
                    or completion_marker_age > CODEX_COMPLETION_MAX_EXIT_SECONDS
                )
            ):
                message = (
                    f"\n⚠️  {timeout_label} 已输出 Codex 完成标记但进程未退出，"
                    "结束子进程并继续 Ralph。\n"
                )
                print(message, end="")
                f.write(message)
                f.flush()
                stop_process(process)
                break

            if (
                AGENT == "codex"
                and completed_by_artifacts
                and idle_time > CODEX_ARTIFACT_COMPLETION_IDLE_SECONDS
            ):
                message = (
                    f"\n⚠️  {timeout_label} 的任务产物已完成但 Codex 进程未退出，"
                    "结束子进程并继续 Ralph。\n"
                )
                print(message, end="")
                f.write(message)
                f.flush()
                stop_process(process)
                break

            if elapsed_time > timeout_seconds:
                timed_out = True
                message = f"\n⚠️  {timeout_label} 超时! 已运行 {int(elapsed_time)} 秒\n"
                print(message, end="")
                f.write(message)
                f.flush()
                stop_process(process)
                break

            time.sleep(1)

    return timed_out


def run_developer(iteration: int, current_story_id: str | None = None) -> tuple[bool, Path]:
    """
    调用开发 Agent
    返回值：是否超时，以及本轮日志路径
    """
    print(f"\n{'='*64}\n  迭代 {iteration}/{MAX_ITERATIONS}\n{'='*64}")
    dev_log = story_log_path(current_story_id, "developer", iteration)
    write_log(dev_log, f"Developer iteration {iteration} started.")

    if not CLAUDE_INSTRUCTION_FILE.exists():
        print(f"❌ 错误: {CLAUDE_INSTRUCTION_FILE} 不存在")
        return False, dev_log

    file_content = CLAUDE_INSTRUCTION_FILE.read_text(encoding="utf-8")
    action_directive = (
        "【执行任务指令】：你将在项目根目录工作，可以修改整个代码库。"
        "需求产物必须使用下面这些显式路径，不要读取或写入其他 Ralph 产物位置。\n"
        f"- Requirement directory: {requirement_path(REQUIREMENT_DIR)}\n"
        f"- PRD JSON: {requirement_path(PRD_FILE)}\n"
        f"- Progress: {requirement_path(PROGRESS_FILE)}\n"
        f"- Screenshots: {requirement_path(SCREENSHOTS_DIR)}\n"
        f"- Logs: {requirement_path(LOGS_DIR)}\n\n"
        "立刻读取 PRD JSON 和 Progress，开始写代码并完成下一个未完成的 User Story。"
        "如果所有任务完成则正常退出。绝对不要进行闲聊或反问。\n\n"
        "=== 基础规则与上下文配置 ===\n"
    )
    prompt = action_directive + file_content
    cmd = build_process_cmd(prompt)

    try:
        process = start_agent_process(cmd, prompt)
        timed_out = stream_process(process, dev_log, TIMEOUT_SECONDS, "开发 Agent")
        if timed_out:
            print("   进程已终止，将在下一次迭代重试")
            write_log(dev_log, "Developer iteration timed out.")
            return True, dev_log

        print("\n✓ 开发迭代完成")
        write_log(dev_log, "Developer iteration completed.")
        return False, dev_log

    except Exception as e:
        print(f"\n❌ 开发 Agent 错误: {e}")
        write_log(dev_log, f"Developer iteration error: {e}")
        return False, dev_log

def run_validator(iteration: int, current_story_id: str | None = None) -> Path | None:
    """
    调用 Validator Agent，传入当前 story ID 以确保验证目标明确
    """
    print(f"\n{'='*64}\n  验证迭代 {iteration} - Validator 开始工作\n{'='*64}")
    validator_log = story_log_path(current_story_id, "validator", iteration)
    write_log(validator_log, f"Validator iteration {iteration} started.")

    if not VALIDATOR_INSTRUCTION_FILE.exists():
        print(f"⚠️  警告: {VALIDATOR_INSTRUCTION_FILE} 不存在，跳过验证")
        write_log(validator_log, "Validator instruction file missing; skipped.")
        return validator_log

    file_content = VALIDATOR_INSTRUCTION_FILE.read_text(encoding="utf-8")
    story_hint = (
        f"\n【当前需要验证的 Story ID 是：{current_story_id}】。"
        "即使 Progress 不存在或为空，也必须验证这个 story，绝不能中止。"
        "请直接读取 PRD JSON 找到该 story 并开始验证。\n"
        if current_story_id
        else ""
    )
    action_directive = (
        "【执行验证任务指令】：你将在项目根目录工作，可以读取和验证整个代码库。"
        "需求产物必须使用下面这些显式路径，不要读取或写入其他 Ralph 产物位置。\n"
        f"- Requirement directory: {requirement_path(REQUIREMENT_DIR)}\n"
        f"- PRD JSON: {requirement_path(PRD_FILE)}\n"
        f"- Progress: {requirement_path(PROGRESS_FILE)}\n"
        f"- Screenshots: {requirement_path(SCREENSHOTS_DIR)}\n"
        f"- Logs: {requirement_path(LOGS_DIR)}\n\n"
        "立刻按照规则对当前 story 进行验收测试，包括运行命令和浏览器测试截图。"
        "千万不要反问或停止确认，遇到问题记录在 notes 字段。验证完成后直接退出。"
        f"{story_hint}\n=== 基础规则与上下文配置 ===\n"
    )
    prompt = action_directive + file_content
    cmd = build_process_cmd(prompt)

    try:
        process = start_agent_process(cmd, prompt)
        timed_out = stream_process(
            process,
            validator_log,
            TIMEOUT_SECONDS * 2,
            "Validator",
            completion_check=all_stories_resolved,
        )
        if timed_out:
            print("   Validator 进程已终止，跳过本次验证")
            write_log(validator_log, "Validator iteration timed out.")
            return validator_log

        print("\n✓ 验证完成")
        write_log(validator_log, "Validator iteration completed.")
        return validator_log

    except Exception as e:
        print(f"\n❌ Validator 错误: {e}")
        write_log(validator_log, f"Validator iteration error: {e}")
        return validator_log


def get_current_story_id() -> str | None:
    """返回 prd.json 中第一个 passes=False 且 blocked=False 的 story ID"""
    try:
        prd = json.loads(PRD_FILE.read_text(encoding="utf-8"))
        for story in prd.get("userStories", []):
            if not story.get("passes", False) and not story.get("blocked", False):
                return story.get("id")
    except Exception:
        pass
    return None


def all_stories_resolved() -> bool:
    """
    检查 prd.json，判断是否所有 story 都已完成或被 blocked
    """
    try:
        prd = json.loads(PRD_FILE.read_text(encoding="utf-8"))
        stories = prd.get("userStories", [])
        for story in stories:
            passes = story.get("passes", False)
            blocked = story.get("blocked", False)
            if not passes and not blocked:
                return False
        return True
    except Exception as e:
        print(f"⚠️  读取 prd.json 失败: {e}")
        return False


def format_duration(seconds: float) -> str:
    """将秒数格式化为易读的时间字符串"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h}小时 {m}分钟 {s}秒"
    elif m > 0:
        return f"{m}分钟 {s}秒"
    else:
        return f"{s}秒"


def wait_for_manual_shutdown(
    total_start_time: float,
    frontend_process: subprocess.Popen | None,
    exit_code: int,
) -> None:
    """任务循环结束后保持 Dashboard 在线，直到用户手动 Ctrl+C。"""
    print("\n📌 Ralph 循环已结束，Dashboard 将继续保持在线。")
    print("   你可以继续在浏览器查看 prd.json、progress.txt 和运行日志。")
    print("   需要退出时，请在当前终端按 Ctrl+C。")

    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        elapsed = time.time() - total_start_time
        print(f"\n\n⚠️  用户关闭 Dashboard")
        print(f"⏱️  总运行时间: {format_duration(elapsed)}")
        stop_process(frontend_process)
        sys.exit(exit_code)


def main():
    """主函数"""
    print(f"启动 Ralph - 最大迭代次数: {MAX_ITERATIONS}")
    print(f"需求目录: {REQUIREMENT_REL.as_posix()}")
    print(f"PRD JSON: {requirement_path(PRD_FILE)}")
    total_start_time = time.time()

    ensure_runtime_artifacts()

    dashboard.start(
        port=ARGS.dashboard_port,
        max_iterations=MAX_ITERATIONS,
        prd_file=PRD_FILE,
        progress_file=PROGRESS_FILE,
    )

    # 自动启动前端服务
    frontend_process = None
    frontend_dir = PROJECT_ROOT / "frontend"
    frontend_log = LOGS_DIR / "frontend-dev.log"
    if frontend_dir.exists() and (frontend_dir / "package.json").exists():
        reusable_port = find_reusable_frontend_port()
        if reusable_port:
            message = f"复用已有前端服务: http://127.0.0.1:{reusable_port}"
            print(f"🌐 {message}")
            write_log(frontend_log, message)
        else:
            print("🌐 正在后台自动启动前端开发服务器...")
            try:
                write_log(frontend_log, "Starting frontend dev server with `npm run dev`.")
                with frontend_log.open("a", encoding="utf-8") as frontend_log_handle:
                    frontend_process = subprocess.Popen(
                        "npm run dev",
                        cwd=str(frontend_dir),
                        shell=True,
                        start_new_session=not is_windows(),
                        stdout=frontend_log_handle,
                        stderr=subprocess.STDOUT,
                    )
                time.sleep(3) # 等待启动完成
            except Exception as e:
                print(f"⚠️ 前端服务后台启动异常: {e}")
                write_log(frontend_log, f"Frontend dev server error: {e}")
    else:
        write_log(frontend_log, "No frontend/package.json found; frontend dev server not started.")

    if all_stories_resolved():
        dashboard.set_state(phase="done", current_story=None)
        print("✅ 当前 prd.json 中所有任务已完成或已标记为 BLOCKED。")
        wait_for_manual_shutdown(total_start_time, frontend_process, exit_code=0)

    for i in range(1, MAX_ITERATIONS + 1):
        try:
            # 第一步：调用开发 Agent
            current_story = get_current_story_id()
            dashboard.set_state(iteration=i, phase="developing", current_story=current_story)
            timed_out, developer_log = run_developer(i, current_story_id=current_story)

            # 开发 Agent 超时，跳过 Validator，直接进入下一次迭代重试
            if timed_out:
                dashboard.set_state(phase="idle", current_story=None)
                print("⏭️  开发 Agent 超时，跳过验证，下一次迭代继续开发...")
                time.sleep(2)
                continue

            # 第二步：开发 Agent 正常完成，调用 Validator Agent
            dashboard.set_state(phase="validating", current_story=current_story)
            validator_log = run_validator(i, current_story_id=current_story)

            # 第三步：检查是否全部完成（passes:true 或 blocked:true）
            dashboard.set_state(phase="idle", current_story=None)
            if all_stories_resolved():
                dashboard.set_state(phase="done", current_story=None)
                elapsed = time.time() - total_start_time
                print("✅ 所有任务已完成或已标记为 BLOCKED!")
                print(f"⏱️  总运行时间: {format_duration(elapsed)}")
                wait_for_manual_shutdown(total_start_time, frontend_process, exit_code=0)

        except KeyboardInterrupt:
            elapsed = time.time() - total_start_time
            print(f"\n\n⚠️  用户中断")
            print(f"⏱️  总运行时间: {format_duration(elapsed)}")
            stop_process(frontend_process)
            sys.exit(130)

    elapsed = time.time() - total_start_time
    print(f"\n已达到最大迭代次数 ({MAX_ITERATIONS})")
    print(f"⏱️  总运行时间: {format_duration(elapsed)}")
    dashboard.set_state(phase="error", current_story=None)
    wait_for_manual_shutdown(total_start_time, frontend_process, exit_code=1)


if __name__ == "__main__":
    main()
