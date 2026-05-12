from __future__ import annotations

from app.security.scanner import (
    SecretScanViolation,
    assert_no_secret_scan_findings,
    redact_sensitive_text,
    scan_text_for_secrets,
)


class TestScanTextForSecrets:
    def test_clean_text_no_findings(self):
        results = scan_text_for_secrets("hello world", source="test.txt")
        assert results == []

    def test_detects_api_key_env_name(self):
        results = scan_text_for_secrets(  # ggignore
            "DEEPSEEK_API_KEY=not_a_real_key", source="test.txt"  # ggignore
        )
        assert any(f.pattern == "provider-env-name" for f in results)

    def test_detects_bearer_token(self):
        results = scan_text_for_secrets(  # ggignore
            "Bearer not_a_real_token_999", source="test.txt"  # ggignore
        )
        assert any(f.pattern == "bearer-token" for f in results)

    def test_detects_openai_style_secret(self):
        results = scan_text_for_secrets(  # ggignore
            "key=sk-00000000FAKE00000000000000", source="test.txt"  # ggignore
        )
        assert any(f.pattern == "openai-style-secret" for f in results)

    def test_detects_memory_customer_canary(self):
        results = scan_text_for_secrets(  # ggignore
            "客户原文 SECRET_DOC_CANARY_demo_123", source="memory"  # ggignore
        )
        assert any(f.pattern == "customer-canary" for f in results)

    def test_detects_dashscope_api_key_env_name(self):
        results = scan_text_for_secrets(  # ggignore
            "DASHSCOPE_API_KEY=not_a_real_key", source="memory"  # ggignore
        )
        assert any(f.pattern == "provider-env-name" for f in results)


class TestRedactSensitiveText:
    def test_redacts_auth_headers_api_keys_and_canaries(self):
        text = (  # ggignore
            "Authorization: Bearer not_a_real_token_999 "
            "api_key=sk-00000000FAKE00000000000000 "
            "SECRET_DOC_CANARY_demo_123"
        )

        redacted = redact_sensitive_text(text)

        assert "Authorization" not in redacted
        assert "Bearer" not in redacted
        assert "api_key" not in redacted
        assert "SECRET_DOC_CANARY" not in redacted
        assert scan_text_for_secrets(redacted, source="memory") == []


class TestAssertNoSecretScanFindings:
    def test_clean_entries_pass(self):
        assert_no_secret_scan_findings([("file.txt", "clean content")])

    def test_dirty_entries_raise(self):
        try:
            assert_no_secret_scan_findings(  # ggignore
                [("file.txt", "Bearer not_a_real_token")]  # ggignore
            )
        except SecretScanViolation:
            pass
        else:
            raise AssertionError("Expected SecretScanViolation")
