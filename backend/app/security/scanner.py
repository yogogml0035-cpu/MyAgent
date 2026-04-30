from __future__ import annotations

import re
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path

SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("provider-env-name", re.compile(r"\b(?:DEEPSEEK_API_KEY|TAVILY_API_KEY)\b")),
    ("authorization-header", re.compile(r"\bAuthorization\b", re.IGNORECASE)),
    ("bearer-token", re.compile(r"\bBearer\s+\S+", re.IGNORECASE)),
    ("openai-style-secret", re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b", re.IGNORECASE)),
    ("api-key-field", re.compile(r"\bapi[_-]?key\b", re.IGNORECASE)),
    ("access-token-field", re.compile(r"\baccess[_-]?token\b", re.IGNORECASE)),
    ("refresh-token-field", re.compile(r"\brefresh[_-]?token\b", re.IGNORECASE)),
)

SESSION_OUTPUT_DIR_NAMES = {"artifacts", "records", "outputs", "agent_workspace"}
TEXT_FILE_SUFFIXES = {
    "",
    ".css",
    ".csv",
    ".html",
    ".json",
    ".jsonl",
    ".log",
    ".md",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
MAX_SCAN_FILE_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class SecretScanFinding:
    source: str
    pattern: str
    excerpt: str


class SecretScanViolation(AssertionError):
    pass


def scan_text_for_secrets(text: str, *, source: str) -> list[SecretScanFinding]:
    findings: list[SecretScanFinding] = []
    for pattern_name, pattern in SECRET_PATTERNS:
        for match in pattern.finditer(text):
            findings.append(
                SecretScanFinding(
                    source=source,
                    pattern=pattern_name,
                    excerpt=_excerpt(text, match.start(), match.end()),
                )
            )
    return findings


def collect_session_output_texts(session_dir: Path) -> Iterator[tuple[str, str]]:
    root = session_dir.resolve()
    events_path = root / "logs" / "events.jsonl"
    if events_path.is_file():
        yield from _read_text_file(events_path, root=root)

    state_path = root / "state.json"
    if state_path.is_file():
        yield from _read_text_file(state_path, root=root)

    for directory_name in SESSION_OUTPUT_DIR_NAMES:
        directory = root / directory_name
        if not directory.exists():
            continue
        for path in sorted(directory.rglob("*")):
            if path.is_file() and _should_scan_file(path):
                yield from _read_text_file(path, root=root)


def assert_no_secret_scan_findings(
    entries: Iterable[tuple[str, str]] | Mapping[str, str],
) -> None:
    items = entries.items() if isinstance(entries, Mapping) else entries
    findings: list[SecretScanFinding] = []
    for source, text in items:
        findings.extend(scan_text_for_secrets(text, source=source))
    if findings:
        detail = "; ".join(
            f"{finding.source}:{finding.pattern}:{finding.excerpt}" for finding in findings[:8]
        )
        raise SecretScanViolation(f"发现敏感凭据输出：{detail}")


def _should_scan_file(path: Path) -> bool:
    try:
        if path.stat().st_size > MAX_SCAN_FILE_BYTES:
            return False
    except OSError:
        return False
    return path.suffix.lower() in TEXT_FILE_SUFFIXES


def _read_text_file(path: Path, *, root: Path) -> Iterator[tuple[str, str]]:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return
    yield str(path.relative_to(root)), text


def _excerpt(text: str, start: int, end: int) -> str:
    prefix = text[max(0, start - 24) : start]
    suffix = text[end : min(len(text), end + 24)]
    return f"{prefix}<match>{suffix}".replace("\n", "\\n")
