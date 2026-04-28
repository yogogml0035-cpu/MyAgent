from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    task_root: Path
    deepseek_api_key: str | None
    deepseek_base_url: str
    tavily_api_key: str | None
    workspace_root: Path
    access_token: str | None = None
    cors_origins: tuple[str, ...] = ("http://localhost:3001", "http://127.0.0.1:3001")
    max_upload_files: int = 10
    max_upload_file_bytes: int = 10 * 1024 * 1024
    max_upload_request_bytes: int = 101 * 1024 * 1024
    max_json_request_bytes: int = 64 * 1024
    deepseek_timeout_seconds: float = 15.0


MODEL_REGISTRY = [
    {
        "id": "deepseek-reasoner",
        "label": "DeepSeek Reasoner",
        "provider": "deepseek",
        "supports_files": True,
        "supports_images": False,
    }
]

WORKER_COUNT_ENV_VARS = ("WEB_CONCURRENCY", "UVICORN_WORKERS", "GUNICORN_WORKERS")


def load_settings() -> Settings:
    backend_root = Path(__file__).resolve().parents[1]
    load_env_file(backend_root / ".env")
    task_root = Path(
        env_value("MYAGENT_TASK_ROOT", "AGENT_CHAT_TASK_ROOT") or backend_root / "storage" / "tasks"
    )
    max_upload_files = read_int_env("MYAGENT_MAX_UPLOAD_FILES", 10, "AGENT_CHAT_MAX_UPLOAD_FILES")
    max_upload_file_bytes = read_int_env(
        "MYAGENT_MAX_UPLOAD_FILE_BYTES",
        10 * 1024 * 1024,
        "AGENT_CHAT_MAX_UPLOAD_FILE_BYTES",
    )
    return Settings(
        task_root=task_root.resolve(),
        deepseek_api_key=os.getenv("DEEPSEEK_API_KEY") or None,
        deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        tavily_api_key=os.getenv("TAVILY_API_KEY") or None,
        workspace_root=task_root.resolve(),
        access_token=env_value("MYAGENT_ACCESS_TOKEN", "AGENT_CHAT_ACCESS_TOKEN") or None,
        cors_origins=read_list_env(
            "MYAGENT_CORS_ORIGINS",
            ("http://localhost:3001", "http://127.0.0.1:3001"),
            "AGENT_CHAT_CORS_ORIGINS",
        ),
        max_upload_files=max_upload_files,
        max_upload_file_bytes=max_upload_file_bytes,
        max_upload_request_bytes=read_int_env(
            "MYAGENT_MAX_UPLOAD_REQUEST_BYTES",
            max_upload_files * max_upload_file_bytes + 1024 * 1024,
            "AGENT_CHAT_MAX_UPLOAD_REQUEST_BYTES",
        ),
        max_json_request_bytes=read_int_env(
            "MYAGENT_MAX_JSON_REQUEST_BYTES",
            64 * 1024,
            "AGENT_CHAT_MAX_JSON_REQUEST_BYTES",
        ),
        deepseek_timeout_seconds=read_float_env("DEEPSEEK_TIMEOUT_SECONDS", 15.0),
    )


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def env_value(primary_name: str, fallback_name: str | None = None) -> str | None:
    return os.getenv(primary_name) or (os.getenv(fallback_name) if fallback_name else None)


def read_int_env(name: str, default: int, fallback_name: str | None = None) -> int:
    raw_value = env_value(name, fallback_name)
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except ValueError:
        return default
    return value if value > 0 else default


def read_list_env(
    name: str, default: tuple[str, ...], fallback_name: str | None = None
) -> tuple[str, ...]:
    raw_value = env_value(name, fallback_name)
    if raw_value is None:
        return default
    values = tuple(
        normalized
        for item in raw_value.split(",")
        if (normalized := item.strip().rstrip("/"))
    )
    return values or default


def enforce_single_process_runtime() -> None:
    for name in WORKER_COUNT_ENV_VARS:
        raw_value = os.getenv(name)
        if raw_value is None:
            continue
        try:
            worker_count = int(raw_value)
        except ValueError:
            continue
        if worker_count > 1:
            raise RuntimeError(
                "MyAgent 使用进程内任务运行器和本地 JSON 任务存储；"
                f"{name}={worker_count} 会把任务状态拆分到多个 worker。"
            )


def read_float_env(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        value = float(raw_value)
    except ValueError:
        return default
    return value if value > 0 else default
