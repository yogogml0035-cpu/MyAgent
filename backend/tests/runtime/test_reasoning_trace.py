from __future__ import annotations

from typing import Any, cast

import httpx
import pytest

from app.agent_activity import build_deep_agent_activity_payload
from app.model_provider import DeepSeekProvider
from app.reasoning_trace import build_reasoning_trace_payload, sanitize_reasoning_text
from app.storage import TaskStorage


def test_reasoning_trace_payload_validates_and_normalizes_safe_fields() -> None:
    payload = build_reasoning_trace_payload(
        agent_id="subagent-quotation",
        phase="observe",
        summary="发现 2 条结构化证据。",
        confidence="medium",
        evidence_refs=["quotation_similarity", {"unsafe": True}, "bidder-a.md"],
        source_event_id="event-1",
    )

    assert payload == {
        "agent_id": "subagent-quotation",
        "phase": "observe",
        "summary": "发现 2 条结构化证据。",
        "confidence": "medium",
        "evidence_refs": ["quotation_similarity", "bidder-a.md"],
        "source_event_id": "event-1",
    }


def test_reasoning_trace_payload_rejects_invalid_phase_or_confidence() -> None:
    with pytest.raises(ValueError, match="phase"):
        build_reasoning_trace_payload(
            agent_id="agent",
            phase=cast(Any, "thinking"),
            summary="摘要",
        )
    with pytest.raises(ValueError, match="confidence"):
        build_reasoning_trace_payload(
            agent_id="agent",
            phase="plan",
            summary="摘要",
            confidence=cast(Any, "certain"),
        )


def test_reasoning_trace_payload_redacts_paths_secrets_and_canaries() -> None:
    payload = build_reasoning_trace_payload(
        agent_id="agent",
        phase="decide",
        summary=(
            "路径 /mnt/d/AgentProject/MyAgent/backend/storage/sessions/task-a 和 "
            "C:\\Users\\0325\\secret.txt 包含 SECRET_DOC_CANARY_123，"
            "Authorization: Bearer abcdefghijklmnop，sk-abcdefghijklmnop。"
        ),
        evidence_refs=[
            "/mnt/d/AgentProject/MyAgent/backend/storage/sessions/task-a/uploads/a.md",
            "RAW_PROMPT_CANARY_456",
        ],
    )
    serialized = str(payload)

    assert "/mnt/d/AgentProject" not in serialized
    assert "C:\\Users" not in serialized
    assert "SECRET_DOC_CANARY_123" not in serialized
    assert "RAW_PROMPT_CANARY_456" not in serialized
    assert "abcdefghijklmnop" not in serialized
    assert "<absolute-path>" in serialized
    assert "<redacted-canary>" in serialized


def test_reasoning_trace_sanitizer_preserves_web_urls_while_redacting_paths() -> None:
    web_url = "http://www.weather.com.cn/weather15d/101121701.shtml"
    secure_url = "https://weather.example/shanghai"
    path_like_urls = [
        "https://example.com/home/user/page",
        "https://example.com/tmp/report",
        "https://example.com/C:/file.txt",
        "https://example.com/a(b)C:/file.txt",
    ]
    sanitized = sanitize_reasoning_text(
        f"来源 {web_url} 和 {secure_url}；本地路径 "
        f"{' '.join(path_like_urls)} "
        r"C:\Users\0325\secret.txt 与 \\server\share\secret.txt，"
        "还有 /mnt/d/private/customer/source.md。"
    )

    assert web_url in sanitized
    assert secure_url in sanitized
    for path_like_url in path_like_urls:
        assert path_like_url in sanitized
    assert "htt<absolute-path>" not in sanitized
    assert r"C:\Users" not in sanitized
    assert r"\\server\share" not in sanitized
    assert "/mnt/d/private" not in sanitized
    assert "<absolute-path>/secret.txt" in sanitized
    assert "<absolute-path>/source.md" in sanitized


def test_reasoning_trace_sanitizer_redacts_unsafe_web_urls() -> None:
    unsafe_urls = [
        "http://localhost/internal",
        "http://127.0.0.1/secret",
        "http://%31%32%37.0.0.1/secret",
        "https://user:pass@example.com/weather",
        "https://@example.com/path",
        "https://:@example.com/path",
        "https://example.com/weather?authorization=secret",
        "https://example.com/weather#access_token=secret",
        "https://example.com/weather#access%5Ftoken=secret",
        "https://example.com/public\nhttp://localhost/admin",
    ]
    sanitized = sanitize_reasoning_text(" ".join(f"[来源]({url})" for url in unsafe_urls))

    for unsafe_url in unsafe_urls:
        assert unsafe_url not in sanitized
    assert sanitized.count("<redacted-url>") == len(unsafe_urls)
    assert "(<redacted-url>)" not in sanitized
    assert "[来源]" not in sanitized


def test_reasoning_trace_sanitizer_unwraps_edge_case_unsafe_markdown_links() -> None:
    long_label = "来源" * 180
    sensitive = sanitize_reasoning_text("[x](https://example.com/a;b?token=secret)")
    long_label_result = sanitize_reasoning_text(
        f"[{long_label}](http://localhost/admin)",
        max_chars=1000,
    )
    local_file_result = sanitize_reasoning_text(
        "[local](/mnt/d/private/secret.txt) [file](file:///C:/secret.txt) [relative](../secret.txt)",
        max_chars=1000,
    )
    nested_result = sanitize_reasoning_text(
        "[outer [inner]](../secret.txt) "
        "[file [inner]](file:///C:/secret.txt) "
        "[local [inner]](http://localhost/admin) "
        "![image](http://localhost/image.png)",
        max_chars=1000,
    )

    assert "https://example.com/a;b?token=secret" not in sensitive
    assert "[x]" not in sensitive
    assert "(<redacted-url>)" not in sensitive
    assert "x（<redacted-url>）" in sensitive
    assert f"[{long_label}]" not in long_label_result
    assert "(<redacted-url>)" not in long_label_result
    assert f"{long_label}（<redacted-url>）" in long_label_result
    assert "[local]" not in local_file_result
    assert "[file]" not in local_file_result
    assert "[relative]" not in local_file_result
    assert "(<absolute-path>" not in local_file_result
    assert "file:///" not in local_file_result
    assert "../secret.txt" not in local_file_result
    assert "local（<redacted-url>）" in local_file_result
    assert "file（<redacted-url>）" in local_file_result
    assert "relative（<redacted-url>）" in local_file_result
    assert "[outer [inner]]" not in nested_result
    assert "[file [inner]]" not in nested_result
    assert "[local [inner]]" not in nested_result
    assert "![image]" not in nested_result
    assert "(<redacted-url>)" not in nested_result
    assert "../secret.txt" not in nested_result
    assert "file:///" not in nested_result
    assert "http://localhost/admin" not in nested_result
    assert r"outer \[inner\]（<redacted-url>）" in nested_result
    assert r"file \[inner\]（<redacted-url>）" in nested_result
    assert r"local \[inner\]（<redacted-url>）" in nested_result
    assert "image（<redacted-url>）" in nested_result


def test_reasoning_trace_sanitizer_preserves_safe_inline_markdown_variants() -> None:
    sanitized = sanitize_reasoning_text(
        '[angle](<https://example.com/page>) [title](https://example.com/page "title") '
        '![image](<https://example.com/image.png>) '
        '[paren](https://example.com/a(b)C:/file.txt)',
        max_chars=1000,
    )

    assert "[angle](https://example.com/page)" in sanitized
    assert "[title](https://example.com/page)" in sanitized
    assert "![image](https://example.com/image.png)" in sanitized
    assert "[paren](https://example.com/a(b)C:/file.txt)" in sanitized
    assert '"title"' not in sanitized
    assert "<redacted-url>" not in sanitized
    assert "<absolute-path>" not in sanitized


def test_reasoning_trace_sanitizer_sanitizes_safe_markdown_link_metadata() -> None:
    sanitized = sanitize_reasoning_text(
        r'[C:\Users\0325\secret.txt](https://example.com/page) '
        '[title](https://example.com/page "http://localhost/admin") '
        '[nested [http://localhost/admin]](https://example.com/page)',
        max_chars=1000,
    )

    assert r"C:\Users" not in sanitized
    assert "http://localhost/admin" not in sanitized
    assert "[<absolute-path>/secret.txt](https://example.com/page)" in sanitized
    assert "[title](https://example.com/page)" in sanitized
    assert r"[nested \[<redacted-url>\]](https://example.com/page)" in sanitized


def test_reasoning_trace_sanitizer_sanitizes_angle_autolinks() -> None:
    sanitized = sanitize_reasoning_text(
        "<https://example.com/home/user/page> "
        "<http://localhost/admin> "
        "<mailto:admin@example.com> "
        "<xmpp:user@example.com> "
        "<javascript:alert(1)> "
        "<data:text/plain,secret> "
        "<https://example.com/weather#access%5Ftoken=secret>",
        max_chars=1000,
    )

    assert "<https://example.com/home/user/page>" in sanitized
    assert "http://localhost/admin" not in sanitized
    assert "mailto:admin@example.com" not in sanitized
    assert "xmpp:user@example.com" not in sanitized
    assert "javascript:alert(1)" not in sanitized
    assert "data:text/plain,secret" not in sanitized
    assert "https://example.com/weather#access%5Ftoken=secret" not in sanitized
    assert sanitized.count("<redacted-url>") == 6
    assert "<<redacted-url>>" not in sanitized
    assert "<absolute-path>" not in sanitized


def test_reasoning_trace_sanitizer_sanitizes_gfm_autolink_literals() -> None:
    safe_www = "www.example.com/home/user/page"
    safe_www_path = "www.example.com/a(b)C:/file.txt"
    sanitized = sanitize_reasoning_text(
        f"{safe_www} {safe_www_path} "
        "www.example.com/weather?token=secret "
        "www.example.com/weather#api%2Dkey=secret "
        "www.localhost/admin "
        "admin@example.com <admin@example.com>",
        max_chars=1000,
    )

    assert safe_www in sanitized
    assert safe_www_path in sanitized
    assert "www.example.com/weather?token=secret" not in sanitized
    assert "www.example.com/weather#api%2Dkey=secret" not in sanitized
    assert "www.localhost/admin" not in sanitized
    assert "admin@example.com" not in sanitized
    assert sanitized.count("<redacted-url>") == 5
    assert "<absolute-path>" not in sanitized


def test_reasoning_trace_sanitizer_sanitizes_reference_style_links() -> None:
    sanitized = sanitize_reasoning_text(
        "\n".join(
            [
                "[安全][safe]",
                "[换行安全][safe-next]",
                "[本机][src]",
                "[相对][rel]",
                "[换行相对][rel-next]",
                "[换行本机][local-next]",
                "[文件][file]",
                r"[转义][a\]b]",
                "",
                "[safe]: https://example.com/home/user/page",
                "[safe-next]:",
                "  https://example.com/tmp/report",
                "[safe-paren]: https://example.com/a(b)C:/file.txt",
                r"[C:\Users\0325\secret.txt]: https://example.com/page",
                '[safe-title]: https://example.com/page "http://localhost/admin"',
                "[safe-trailing]: https://example.com/page trailing http://localhost/admin",
                "[src]: http://localhost/admin",
                "[rel]: ../secret.txt",
                "[rel-next]:",
                "../secret.txt",
                "[local-next]:",
                "http://localhost/admin",
                "[file]: file:///C:/secret.txt",
                r"[a\]b]: http://localhost/admin",
            ]
        ),
        max_chars=1000,
    )

    assert "[safe]: https://example.com/home/user/page" in sanitized
    assert "[safe-next]: https://example.com/tmp/report" in sanitized
    assert "[safe-paren]: https://example.com/a(b)C:/file.txt" in sanitized
    assert "[<absolute-path>/secret.txt]: https://example.com/page" in sanitized
    assert "[safe-title]: https://example.com/page" in sanitized
    assert "[safe-trailing]: https://example.com/page" in sanitized
    assert r"C:\Users" not in sanitized
    assert "[src]:" not in sanitized
    assert "[rel]:" not in sanitized
    assert "[rel-next]:" not in sanitized
    assert "[local-next]:" not in sanitized
    assert "[file]:" not in sanitized
    assert r"[a\]b]:" not in sanitized
    assert "http://localhost/admin" not in sanitized
    assert "../secret.txt" not in sanitized
    assert "file:///" not in sanitized
    assert "https://example.com/a(b)<absolute-path>" not in sanitized
    assert "src（<redacted-url>）" in sanitized
    assert "rel（<redacted-url>）" in sanitized
    assert "rel-next（<redacted-url>）" in sanitized
    assert "local-next（<redacted-url>）" in sanitized
    assert "file（<redacted-url>）" in sanitized
    assert r"a\]b（<redacted-url>）" in sanitized


def test_reasoning_trace_sanitizer_restores_more_than_ten_web_urls() -> None:
    urls = [f"https://example.com/home/user/page-{index}" for index in range(12)]
    sanitized = sanitize_reasoning_text(" ".join(urls), max_chars=1000)

    for url in urls:
        assert url in sanitized
    assert "MYAGENTURLPLACEHOLDER" not in sanitized
    assert "<absolute-path>" not in sanitized


def test_reasoning_trace_sanitizer_does_not_restore_placeholder_text_inside_urls() -> None:
    first = "https://example.com/MYAGENTURLPLACEHOLDER_1_/page"
    second = "https://safe.example/path"
    sanitized = sanitize_reasoning_text(f"{first} {second}", max_chars=1000)

    assert first in sanitized
    assert second in sanitized
    assert "https://example.com/https://safe.example/path/page" not in sanitized


def test_reasoning_trace_payload_truncates_overlong_summary() -> None:
    payload = build_reasoning_trace_payload(
        agent_id="agent",
        phase="final_summary",
        summary="x" * 800,
    )

    assert len(payload["summary"]) <= 360
    assert payload["summary"].endswith("…")


def test_deep_agent_activity_payload_redacts_and_truncates_safe_fields() -> None:
    payload = build_deep_agent_activity_payload(
        activity_kind="progress",
        phase="tool_use",
        status="running",
        title="工具调用准备",
        summary=(
            "路径 /mnt/d/AgentProject/MyAgent/backend/storage/sessions/task-a 和 "
            "C:\\Users\\0325\\secret.txt 包含 SECRET_DOC_CANARY_123，"
            "Authorization: Bearer abcdefghijklmnop，sk-abcdefghijklmnop。"
        ),
        tool_name="read_file",
        parameter_summary="/conversation_history/raw prompt " + "x" * 400,
        result_summary="CUSTOMER_SAFE_METADATA_ONLY",
        subgraph_path=["agent", "file-record-agent", "/mnt/d/private/path"],
        source_event_id="event-1",
    )
    serialized = str(payload)

    assert payload["schema_version"] == 1
    assert payload["source"] == "deepagents"
    assert payload["truncated"] is True
    assert "/mnt/d/AgentProject" not in serialized
    assert "C:\\Users" not in serialized
    assert "SECRET_DOC_CANARY_123" not in serialized
    assert "abcdefghijklmnop" not in serialized
    assert "conversation_history/raw" not in serialized
    assert "<absolute-path>" in serialized
    assert "<redacted-canary>" in serialized
    assert "<deepagents-internal>" in serialized


def test_deep_agent_activity_payload_requires_summary() -> None:
    with pytest.raises(ValueError, match="summary"):
        build_deep_agent_activity_payload(
            activity_kind="progress",
            phase="tool_use",
            status="running",
            title="工具调用准备",
        )


def test_task_storage_appends_fixed_reasoning_trace_event(tmp_path) -> None:
    storage = TaskStorage(tmp_path / "sessions")
    state = storage.create_task(None, "deepseek-reasoner")
    started = storage.start_run(
        state.task_id,
        message="hello",
        model="deepseek-reasoner",
        expected_statuses={"idle"},
    )
    assert started is not None
    _, run_id = started

    event = storage.append_reasoning_trace(
        state.task_id,
        run_id,
        agent_id="agent",
        phase="plan",
        summary="开始规划。",
        evidence_refs=["uploads/a.md"],
    )

    assert event.type == "reasoning_trace"
    assert event.run_id == run_id
    assert event.payload["phase"] == "plan"
    assert event.payload["evidence_refs"] == ["uploads/a.md"]


def test_deepseek_extract_content_ignores_reasoning_content_canary() -> None:
    response = httpx.Response(
        200,
        json={
            "choices": [
                {
                    "message": {
                        "reasoning_content": "RAW_REASONING_CONTENT_CANARY_SHOULD_NOT_APPEAR",
                        "content": "安全最终回答。",
                    }
                }
            ]
        },
    )

    content = DeepSeekProvider._extract_content(response)

    assert content == "安全最终回答。"
    assert "RAW_REASONING_CONTENT_CANARY_SHOULD_NOT_APPEAR" not in content
