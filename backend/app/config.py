"""Application configuration for the DeepAgents-powered MyAgent platform.

Supersedes the old settings.py with multi-model support and DeepAgents-specific settings.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """Runtime configuration loaded from environment variables and .env file."""

    task_root: Path
    workspace_root: Path
    database_url: str | None = None
    qdrant_url: str | None = None
    qdrant_collection: str = "myagent_memories"

    # Model provider keys
    deepseek_api_key: str | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    tavily_api_key: str | None = None
    dashscope_api_key: str | None = None
    embedding_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    embedding_model: str = "text-embedding-v3"
    embedding_dimensions: int = 1024

    # Agent defaults
    default_model: str = "deepseek:deepseek-chat"
    skills_dirs: tuple[str, ...] = ("./skills",)
    max_concurrent_subagents: int = 3
    agent_timeout_seconds: float = 300.0

    # Security
    access_token: str | None = None
    cors_origins: tuple[str, ...] = ("http://localhost:3001", "http://127.0.0.1:3001")

    # Upload limits
    max_upload_files: int = 10
    max_upload_file_bytes: int = 10 * 1024 * 1024
    max_upload_request_bytes: int = 101 * 1024 * 1024
    max_json_request_bytes: int = 64 * 1024


MODEL_REGISTRY = [
    {
        "id": "deepseek:deepseek-chat",
        "label": "DeepSeek Chat",
        "provider": "deepseek",
        "supports_files": True,
        "supports_images": False,
    },
    {
        "id": "deepseek:deepseek-reasoner",
        "label": "DeepSeek Reasoner",
        "provider": "deepseek",
        "supports_files": True,
        "supports_images": False,
    },
    {
        "id": "openai:gpt-4o",
        "label": "GPT-4o",
        "provider": "openai",
        "supports_files": True,
        "supports_images": True,
    },
    {
        "id": "openai:gpt-4o-mini",
        "label": "GPT-4o Mini",
        "provider": "openai",
        "supports_files": True,
        "supports_images": True,
    },
    {
        "id": "anthropic:claude-sonnet-4-20250514",
        "label": "Claude Sonnet 4",
        "provider": "anthropic",
        "supports_files": True,
        "supports_images": True,
    },
]

WORKER_COUNT_ENV_VARS = ("WEB_CONCURRENCY", "UVICORN_WORKERS", "GUNICORN_WORKERS")


def load_settings() -> Settings:
    """Load settings from .env file and environment variables."""
    backend_root = Path(__file__).resolve().parents[1]
    load_env_file(backend_root / ".env")
    task_root = Path(
        env_value("MYAGENT_TASK_ROOT", "AGENT_CHAT_TASK_ROOT")
        or str(backend_root / "storage" / "sessions")
    )
    max_upload_files = read_int_env("MYAGENT_MAX_UPLOAD_FILES", 10, "AGENT_CHAT_MAX_UPLOAD_FILES")
    max_upload_file_bytes = read_int_env(
        "MYAGENT_MAX_UPLOAD_FILE_BYTES",
        10 * 1024 * 1024,
        "AGENT_CHAT_MAX_UPLOAD_FILE_BYTES",
    )
    skills_raw = os.getenv("MYAGENT_SKILLS_DIRS", "./skills")
    skills_dirs = tuple(s.strip() for s in skills_raw.split(",") if s.strip()) or ("./skills",)
    return Settings(
        task_root=task_root.resolve(),
        workspace_root=task_root.resolve(),
        database_url=env_value("MYAGENT_DATABASE_URL", "DATABASE_URL") or None,
        qdrant_url=os.getenv("MYAGENT_QDRANT_URL") or None,
        qdrant_collection=os.getenv("MYAGENT_QDRANT_COLLECTION", "myagent_memories"),
        deepseek_api_key=os.getenv("DEEPSEEK_API_KEY") or None,
        deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        openai_api_key=os.getenv("OPENAI_API_KEY") or None,
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY") or None,
        tavily_api_key=os.getenv("TAVILY_API_KEY") or None,
        dashscope_api_key=os.getenv("DASHSCOPE_API_KEY") or None,
        embedding_base_url=os.getenv(
            "MYAGENT_EMBEDDING_BASE_URL",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        ),
        embedding_model=os.getenv("MYAGENT_EMBEDDING_MODEL", "text-embedding-v3"),
        embedding_dimensions=read_int_env("MYAGENT_EMBEDDING_DIMENSIONS", 1024),
        default_model=os.getenv("MYAGENT_DEFAULT_MODEL", "deepseek:deepseek-chat"),
        skills_dirs=skills_dirs,
        max_concurrent_subagents=read_int_env("MYAGENT_MAX_CONCURRENT_SUBAGENTS", 3),
        agent_timeout_seconds=read_float_env("MYAGENT_AGENT_TIMEOUT_SECONDS", 300.0),
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
    )


def load_env_file(path: Path) -> None:
    """Load key=value pairs from a .env file into os.environ (without overwriting)."""
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
    """Read an environment variable with optional fallback name."""
    return os.getenv(primary_name) or (os.getenv(fallback_name) if fallback_name else None)


def read_int_env(name: str, default: int, fallback_name: str | None = None) -> int:
    """Read a positive integer from an environment variable."""
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
    """Read a comma-separated list from an environment variable."""
    raw_value = env_value(name, fallback_name)
    if raw_value is None:
        return default
    values = tuple(
        normalized for item in raw_value.split(",") if (normalized := item.strip().rstrip("/"))
    )
    return values or default


def read_float_env(name: str, default: float) -> float:
    """Read a positive float from an environment variable."""
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        value = float(raw_value)
    except ValueError:
        return default
    return value if value > 0 else default


def enforce_single_process_runtime() -> None:
    """Reject multi-worker deployments that would break the in-process runner."""
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
                "MyAgent 使用进程内任务运行器和 Postgres 任务存储；"
                f"{name}={worker_count} 会把任务状态拆分到多个 worker。"
            )
