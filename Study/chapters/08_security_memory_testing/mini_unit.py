import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
ALLOWED_MEMORY_TYPES = {"preference", "profile_fact", "project_rule", "stable_workflow"}
SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{8,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._-]+", re.IGNORECASE),
]


def has_secret(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def should_store_memory(memory_type: str, text: str, confidence: float) -> bool:
    if memory_type not in ALLOWED_MEMORY_TYPES:
        return False
    if confidence < 0.72:
        return False
    if has_secret(text):
        return False
    return bool(text.strip())


def assert_source_contracts() -> None:
    main = (REPO_ROOT / "backend/app/main.py").read_text(encoding="utf-8")
    memory = (REPO_ROOT / "backend/app/memory.py").read_text(encoding="utf-8")
    scanner = (REPO_ROOT / "backend/app/security/scanner.py").read_text(encoding="utf-8")
    frontend_package = (REPO_ROOT / "frontend/package.json").read_text(encoding="utf-8")

    assert "def authorize_task_request" in main
    assert "request.query_params.get(\"token\")" in main
    assert "is_local_client(request)" in main
    assert "MEMORY_TYPES" in memory
    for memory_type in ALLOWED_MEMORY_TYPES:
        assert f'"{memory_type}"' in memory
    assert "scan_text_for_secrets" in memory
    assert "redact_sensitive_text" in memory
    assert "scan_text_for_secrets" in scanner
    assert "--max-warnings=0" in frontend_package


if __name__ == "__main__":
    assert should_store_memory("project_rule", "用户要求所有前端视觉改动先读 DESIGN.md", 0.95)
    assert not should_store_memory("temporary_fact", "今天下雨", 0.95)
    assert not should_store_memory("preference", "我的 key 是 sk-abcdefghi", 0.99)
    assert not should_store_memory("stable_workflow", "置信度太低", 0.2)
    assert_source_contracts()

    print("OK: 你已经理解长期记忆的类型白名单、置信度和敏感信息过滤。")
