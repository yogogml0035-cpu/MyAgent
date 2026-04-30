from __future__ import annotations

import ipaddress
import re
from collections.abc import Callable, Iterable
from typing import Any, Literal
from urllib.parse import parse_qsl, urlsplit

ReasoningPhase = Literal["plan", "observe", "decide", "next_step", "final_summary", "risk"]
ReasoningConfidence = Literal["low", "medium", "high"]
ReasoningEmit = Callable[[str, str, dict[str, Any] | None], Any]

REASONING_PHASES: set[str] = {"plan", "observe", "decide", "next_step", "final_summary", "risk"}
REASONING_CONFIDENCES: set[str] = {"low", "medium", "high"}
PHASE_LABELS: dict[ReasoningPhase, str] = {
    "plan": "计划",
    "observe": "观察",
    "decide": "决策",
    "next_step": "下一步",
    "final_summary": "总结",
    "risk": "风险",
}
MAX_REASONING_SUMMARY_CHARS = 360
MAX_EXCEPTION_SUMMARY_CHARS = 240
MAX_EVIDENCE_REFS = 12
MAX_EVIDENCE_REF_CHARS = 120
URL_PLACEHOLDER_PREFIX = "\x00MYAGENTURLPLACEHOLDER_"
URL_PLACEHOLDER_SUFFIX = "\x00"
URL_REDACTION = "<redacted-url>"
SENSITIVE_URL_QUERY_KEY_MARKERS = ("token", "secret", "password", "credential")
SENSITIVE_URL_ASSIGNMENT_PATTERN = re.compile(
    r"(?:^|[?&;#])(?:authorization|auth(?:[_-][^=;&?#]*)?|access[_-]?token|api[_-]?key|apikey|key|token|secret|password|credential)=",
    re.IGNORECASE,
)

CANARY_PATTERN = re.compile(
    r"\b(?:SECRET_DOC_CANARY|RAW_PROMPT_CANARY|PROVIDER_KEY_CANARY|AUTH_HEADER_CANARY)"
    r"_[A-Za-z0-9_-]+\b",
    re.IGNORECASE,
)
WINDOWS_PATH_PATTERN = re.compile(
    r"(?P<path>(?:(?<![A-Za-z0-9])[A-Za-z]:[\\/]|\\\\)[^\s\"'，。；;]*)"
)
POSIX_PRIVATE_PATH_PATTERN = re.compile(
    r"(?P<path>/(?:mnt|home|Users|var|tmp|root|private|workspace)(?:/[^\s\"'，。；;]+)+)"
)
AUTH_VALUE_PATTERN = re.compile(
    r"\b(?P<name>Authorization|X-MyAgent-Token)\s*[:=]\s*(?P<value>(?:Bearer\s+)?[^\s,;，。]+)",
    re.IGNORECASE,
)
SECRET_VALUE_PATTERN = re.compile(r"\b(?:sk|pk|api|key)-[A-Za-z0-9_-]{8,}\b", re.IGNORECASE)
WEB_URL_PATTERN = re.compile(r"https?://[^\s\"'<>，。]+", re.IGNORECASE)
GFM_WWW_AUTOLINK_PATTERN = re.compile(r"(?<![A-Za-z0-9@:/])www\.[^\s\"'<>，。]+", re.IGNORECASE)
GFM_EMAIL_AUTOLINK_PATTERN = re.compile(
    r"(?<![A-Za-z0-9._%+-])<?"
    r"(?P<email>[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)"
    r">?(?![A-Za-z0-9._%+-])"
)
ANGLE_AUTOLINK_PATTERN = re.compile(
    r"<(?P<destination>[A-Za-z][A-Za-z0-9+.-]{1,31}:[^\s<>]*)>"
)
REFERENCE_LINK_DEFINITION_PATTERN = re.compile(
    r"(?m)^(?P<indent>[ \t]{0,3})\[(?P<label>(?:\\.|[^\]\\\n])+)\]:[ \t]*"
    r"(?:(?P<destination><[^>\n]*>|[^\s\n]+)(?P<title>[^\n]*)|"
    r"[ \t]*\n[ \t]*(?P<next_destination><[^>\n]*>|[^\s\n]+)(?P<next_title>[^\n]*))$"
)
REDACTED_MARKDOWN_LINK_PATTERN = re.compile(
    rf"(?<!!)\[([^\]]*)\]\([^)]*{re.escape(URL_REDACTION)}[^)]*\)",
    re.DOTALL,
)


def build_reasoning_trace_payload(
    *,
    agent_id: str,
    phase: str,
    summary: str,
    confidence: str | None = None,
    evidence_refs: Iterable[Any] | None = None,
    source_event_id: str | None = None,
) -> dict[str, Any]:
    normalized_agent_id = sanitize_reasoning_text(agent_id, max_chars=120)
    normalized_phase = phase.strip()
    normalized_summary = sanitize_reasoning_text(summary, max_chars=MAX_REASONING_SUMMARY_CHARS)
    normalized_confidence = confidence.strip() if isinstance(confidence, str) else None

    if not normalized_agent_id:
        raise ValueError("reasoning_trace.agent_id 不能为空")
    if normalized_phase not in REASONING_PHASES:
        raise ValueError(f"reasoning_trace.phase 无效：{phase}")
    if not normalized_summary:
        raise ValueError("reasoning_trace.summary 不能为空")
    if normalized_confidence is not None and normalized_confidence not in REASONING_CONFIDENCES:
        raise ValueError(f"reasoning_trace.confidence 无效：{confidence}")

    payload: dict[str, Any] = {
        "agent_id": normalized_agent_id,
        "phase": normalized_phase,
        "summary": normalized_summary,
        "evidence_refs": sanitize_evidence_refs(evidence_refs or []),
    }
    if normalized_confidence is not None:
        payload["confidence"] = normalized_confidence
    if isinstance(source_event_id, str) and source_event_id.strip():
        payload["source_event_id"] = sanitize_reasoning_text(source_event_id, max_chars=120)
    return payload


def emit_reasoning_trace(
    emit: ReasoningEmit,
    *,
    agent_id: str,
    phase: ReasoningPhase,
    summary: str,
    confidence: ReasoningConfidence | None = None,
    evidence_refs: Iterable[Any] | None = None,
    source_event_id: str | None = None,
) -> Any:
    payload = build_reasoning_trace_payload(
        agent_id=agent_id,
        phase=phase,
        summary=summary,
        confidence=confidence,
        evidence_refs=evidence_refs,
        source_event_id=source_event_id,
    )
    label = PHASE_LABELS[phase]
    return emit(
        "reasoning_trace",
        f"{payload['agent_id']} 已记录{label}思考摘要。",
        payload,
    )


def sanitize_evidence_refs(values: Iterable[Any]) -> list[str]:
    refs: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        sanitized = sanitize_reasoning_text(value, max_chars=MAX_EVIDENCE_REF_CHARS)
        if sanitized:
            refs.append(sanitized)
        if len(refs) >= MAX_EVIDENCE_REFS:
            break
    return refs


def build_safe_exception_payload(
    exc: BaseException,
    *,
    max_chars: int = MAX_EXCEPTION_SUMMARY_CHARS,
) -> dict[str, str]:
    error_type = re.sub(r"[^A-Za-z0-9_.-]+", "_", type(exc).__name__)[:120] or "Exception"
    error = sanitize_reasoning_text(str(exc), max_chars=max_chars) or error_type
    return {"error_type": error_type, "error": error}


def sanitize_reasoning_text(value: str, *, max_chars: int = MAX_REASONING_SUMMARY_CHARS) -> str:
    text = value.strip()
    if not text:
        return ""
    text = CANARY_PATTERN.sub("<redacted-canary>", text)
    protected_segments: list[str] = []
    text = _sanitize_markdown_reference_links(text, protected_segments)
    text = _sanitize_markdown_web_links(text, protected_segments)
    text = _sanitize_angle_autolinks(text, protected_segments)
    text = _protect_web_urls(text, protected_segments)
    text = _sanitize_gfm_www_autolinks(text, protected_segments)
    text = _sanitize_gfm_email_autolinks(text)
    text = AUTH_VALUE_PATTERN.sub(lambda match: f"{match.group('name')}:<redacted>", text)
    text = SECRET_VALUE_PATTERN.sub("<redacted-secret>", text)
    text = WINDOWS_PATH_PATTERN.sub(lambda match: _redact_path(match.group("path")), text)
    text = POSIX_PRIVATE_PATH_PATTERN.sub(lambda match: _redact_path(match.group("path")), text)
    text = _restore_protected_segments(text, protected_segments)
    text = _unwrap_redacted_markdown_links(text)
    if len(text) > max_chars:
        return text[: max_chars - 1].rstrip() + "…"
    return text


def sanitize_public_web_url(value: object, *, max_chars: int | None = None) -> str:
    raw = str(value or "").strip()
    if not raw or (max_chars is not None and len(raw) > max_chars):
        return ""
    if any(ord(char) <= 32 or ord(char) == 127 for char in raw):
        return ""
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return ""
    if parsed.scheme.casefold() not in {"http", "https"}:
        return ""
    if SENSITIVE_URL_ASSIGNMENT_PATTERN.search(raw):
        return ""
    if AUTH_VALUE_PATTERN.search(raw) or SECRET_VALUE_PATTERN.search(raw):
        return ""
    host = parsed.hostname
    if not host or _is_unsafe_web_host(host):
        return ""
    if "@" in parsed.netloc or parsed.username is not None or parsed.password is not None:
        return ""
    if _has_sensitive_query_key(parsed.query) or _has_sensitive_query_key(parsed.fragment):
        return ""
    return raw


def _sanitize_markdown_web_links(text: str, protected_segments: list[str]) -> str:
    output: list[str] = []
    cursor = 0
    while cursor < len(text):
        is_image = text.startswith("![", cursor)
        link_start = cursor + 1 if is_image else cursor
        if text[link_start] != "[":
            output.append(text[cursor])
            cursor += 1
            continue
        label_end = _find_markdown_label_end(text, link_start)
        if label_end is None or label_end + 1 >= len(text) or text[label_end + 1] != "(":
            output.append(text[cursor])
            cursor += 1
            continue
        destination_end = _find_markdown_destination_end(text, label_end + 1)
        if destination_end is None:
            output.append(text[cursor])
            cursor += 1
            continue
        label = text[link_start + 1 : label_end]
        destination = _inline_destination_value(text[label_end + 2 : destination_end])
        if sanitize_public_web_url(destination):
            output.append(
                _protect_segment(
                    protected_segments,
                    _build_safe_inline_markdown_link(
                        is_image=is_image,
                        label=label,
                        destination=destination,
                    ),
                )
            )
        else:
            output.append(f"{_safe_visible_markdown_label(label)}（{URL_REDACTION}）")
        cursor = destination_end + 1
    return "".join(output)


def _safe_visible_markdown_label(label: str) -> str:
    label = _decode_markdown_label_escapes(label)
    sanitized = sanitize_reasoning_text(
        label,
        max_chars=max(MAX_REASONING_SUMMARY_CHARS, len(label) * 2 + 120),
    )
    return sanitized.replace("[", r"\[").replace("]", r"\]")


def _decode_markdown_label_escapes(label: str) -> str:
    return re.sub(r"\\([\\`*{}\[\]()#+\-.!_>~|:])", r"\1", label)


def _build_safe_inline_markdown_link(*, is_image: bool, label: str, destination: str) -> str:
    prefix = "!" if is_image else ""
    return f"{prefix}[{_safe_visible_markdown_label(label)}]({destination})"


def _find_markdown_label_end(text: str, start: int) -> int | None:
    depth = 0
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == "[":
            depth += 1
            continue
        if char == "]":
            depth -= 1
            if depth == 0:
                return index
            if depth < 0:
                return None
    return None


def _find_markdown_destination_end(text: str, open_paren: int) -> int | None:
    depth = 0
    escaped = False
    for index in range(open_paren, len(text)):
        char = text[index]
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == "(":
            depth += 1
            continue
        if char == ")":
            depth -= 1
            if depth == 0:
                return index
            if depth < 0:
                return None
    return None


def _inline_destination_value(raw_destination: str) -> str:
    value = raw_destination.strip()
    if value.startswith("<"):
        closing = value.find(">")
        if closing > 0:
            title = value[closing + 1 :].strip()
            if title and not _is_markdown_title(title):
                return ""
            return value[1:closing].strip()
        return value
    if not value:
        return ""
    parts = value.split(maxsplit=1)
    if len(parts) == 1:
        return parts[0]
    if not _is_markdown_title(parts[1].strip()):
        return ""
    return parts[0]


def _is_markdown_title(value: str) -> bool:
    if len(value) < 2:
        return False
    return value[0] == value[-1] and value[0] in {"'", '"'}


def _sanitize_markdown_reference_links(text: str, protected_segments: list[str]) -> str:
    def replace(match: re.Match[str]) -> str:
        destination = _reference_destination_value(
            match.group("destination") or match.group("next_destination") or ""
        )
        if sanitize_public_web_url(destination):
            return _protect_segment(
                protected_segments,
                f"{match.group('indent')}[{_safe_visible_markdown_label(match.group('label'))}]: {destination}",
            )
        return f"{match.group('indent')}{_safe_visible_markdown_label(match.group('label'))}（{URL_REDACTION}）"

    return REFERENCE_LINK_DEFINITION_PATTERN.sub(replace, text)


def _sanitize_angle_autolinks(text: str, protected_segments: list[str]) -> str:
    def replace(match: re.Match[str]) -> str:
        safe_url = sanitize_public_web_url(match.group("destination"))
        if safe_url:
            return _protect_segment(protected_segments, f"<{safe_url}>")
        return URL_REDACTION

    return ANGLE_AUTOLINK_PATTERN.sub(replace, text)


def _reference_destination_value(destination: str) -> str:
    value = destination.strip()
    if value.startswith("<") and value.endswith(">"):
        return value[1:-1].strip()
    return value


def _protect_web_urls(text: str, protected_segments: list[str]) -> str:
    def replace(match: re.Match[str]) -> str:
        candidate, suffix = _split_bare_url_candidate(match.group(0))
        safe_url = sanitize_public_web_url(candidate)
        if not safe_url:
            return f"{URL_REDACTION}{suffix}"
        return f"{_protect_segment(protected_segments, safe_url)}{suffix}"

    return WEB_URL_PATTERN.sub(replace, text)


def _sanitize_gfm_www_autolinks(text: str, protected_segments: list[str]) -> str:
    def replace(match: re.Match[str]) -> str:
        candidate, suffix = _split_bare_url_candidate(match.group(0))
        if not sanitize_public_web_url(f"https://{candidate}"):
            return f"{URL_REDACTION}{suffix}"
        return f"{_protect_segment(protected_segments, candidate)}{suffix}"

    return GFM_WWW_AUTOLINK_PATTERN.sub(replace, text)


def _sanitize_gfm_email_autolinks(text: str) -> str:
    return GFM_EMAIL_AUTOLINK_PATTERN.sub(URL_REDACTION, text)


def _split_bare_url_candidate(value: str) -> tuple[str, str]:
    candidate = value
    suffix = ""
    while candidate:
        tail = candidate[-1]
        if tail in ".,!?，。；;:":
            suffix = tail + suffix
            candidate = candidate[:-1]
            continue
        if tail == ")" and candidate.count("(") < candidate.count(")"):
            suffix = tail + suffix
            candidate = candidate[:-1]
            continue
        if tail == "]" and candidate.count("[") < candidate.count("]"):
            suffix = tail + suffix
            candidate = candidate[:-1]
            continue
        break
    return candidate, suffix


def _protect_segment(protected_segments: list[str], value: str) -> str:
    protected_segments.append(value)
    return f"{URL_PLACEHOLDER_PREFIX}{len(protected_segments) - 1}{URL_PLACEHOLDER_SUFFIX}"


def _restore_protected_segments(text: str, protected_segments: list[str]) -> str:
    for index, value in enumerate(protected_segments):
        text = text.replace(f"{URL_PLACEHOLDER_PREFIX}{index}{URL_PLACEHOLDER_SUFFIX}", value)
    return text


def _unwrap_redacted_markdown_links(text: str) -> str:
    return REDACTED_MARKDOWN_LINK_PATTERN.sub(
        lambda match: f"{match.group(1)}（{URL_REDACTION}）",
        text,
    )


def _is_unsafe_web_host(host: str) -> bool:
    normalized = host.rstrip(".").casefold()
    if "%" in normalized:
        return True
    if normalized in {"localhost"} or normalized.endswith(".localhost"):
        return True
    if normalized.endswith(".local"):
        return True
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        if "." not in normalized:
            return True
        return _is_ambiguous_numeric_host(normalized)
    return any(
        (
            address.is_loopback,
            address.is_private,
            address.is_link_local,
            address.is_multicast,
            address.is_unspecified,
            address.is_reserved,
        )
    )


def _is_ambiguous_numeric_host(host: str) -> bool:
    labels = host.split(".")
    if not labels:
        return False
    return all(_is_numeric_host_label(label) for label in labels)


def _is_numeric_host_label(label: str) -> bool:
    if not label:
        return False
    if label.isdigit():
        return True
    if label.startswith("0x") and len(label) > 2:
        return all(char in "0123456789abcdef" for char in label[2:])
    return False


def _has_sensitive_query_key(query: str) -> bool:
    if not query:
        return False
    for key, _value in parse_qsl(query, keep_blank_values=True):
        folded = key.strip().casefold().replace("-", "_")
        compact = folded.replace("_", "")
        if any(marker in folded for marker in SENSITIVE_URL_QUERY_KEY_MARKERS):
            return True
        if folded == "authorization":
            return True
        if folded == "auth" or folded.startswith("auth_") or folded.endswith("_auth"):
            return True
        if folded == "key" or folded.endswith("_key") or compact == "apikey":
            return True
    return False


def _redact_path(path: str) -> str:
    normalized = path.rstrip("\\/")
    if not normalized:
        return "<absolute-path>"
    name = re.split(r"[\\/]", normalized)[-1] or "<root>"
    return f"<absolute-path>/{name}"
