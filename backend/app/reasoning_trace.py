from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from typing import Any, Literal

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
MAX_EVIDENCE_REFS = 12
MAX_EVIDENCE_REF_CHARS = 120

CANARY_PATTERN = re.compile(
    r"\b(?:SECRET_DOC_CANARY|RAW_PROMPT_CANARY|PROVIDER_KEY_CANARY|AUTH_HEADER_CANARY)"
    r"_[A-Za-z0-9_-]+\b",
    re.IGNORECASE,
)
WINDOWS_PATH_PATTERN = re.compile(
    r"(?P<path>(?:[A-Za-z]:[\\/]|\\\\)[^\s\"'，。；;]*)"
)
POSIX_PRIVATE_PATH_PATTERN = re.compile(
    r"(?P<path>/(?:mnt|home|Users|var|tmp|root|private|workspace)(?:/[^\s\"'，。；;]+)+)"
)
AUTH_VALUE_PATTERN = re.compile(
    r"\b(?P<name>Authorization|X-MyAgent-Token)\s*[:=]\s*(?P<value>(?:Bearer\s+)?[^\s,;，。]+)",
    re.IGNORECASE,
)
SECRET_VALUE_PATTERN = re.compile(r"\b(?:sk|pk|api|key)-[A-Za-z0-9_-]{8,}\b", re.IGNORECASE)


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


def sanitize_reasoning_text(value: str, *, max_chars: int = MAX_REASONING_SUMMARY_CHARS) -> str:
    text = value.strip()
    if not text:
        return ""
    text = CANARY_PATTERN.sub("<redacted-canary>", text)
    text = AUTH_VALUE_PATTERN.sub(lambda match: f"{match.group('name')}:<redacted>", text)
    text = SECRET_VALUE_PATTERN.sub("<redacted-secret>", text)
    text = WINDOWS_PATH_PATTERN.sub(lambda match: _redact_path(match.group("path")), text)
    text = POSIX_PRIVATE_PATH_PATTERN.sub(lambda match: _redact_path(match.group("path")), text)
    if len(text) > max_chars:
        return text[: max_chars - 1].rstrip() + "…"
    return text


def _redact_path(path: str) -> str:
    normalized = path.rstrip("\\/")
    if not normalized:
        return "<absolute-path>"
    name = re.split(r"[\\/]", normalized)[-1] or "<root>"
    return f"<absolute-path>/{name}"
