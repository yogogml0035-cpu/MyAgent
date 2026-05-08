from __future__ import annotations

from app.security.scanner import (
    SecretScanFinding,
    SecretScanViolation,
    assert_no_secret_scan_findings,
    scan_text_for_secrets,
)


class TestScanTextForSecrets:
    def test_clean_text_no_findings(self):
        results = scan_text_for_secrets("hello world", source="test.txt")
        assert results == []

    def test_detects_api_key_env_name(self):
        results = scan_text_for_secrets("DEEPSEEK_API_KEY=abc123", source="test.txt")
        assert any(f.pattern == "provider-env-name" for f in results)

    def test_detects_bearer_token(self):
        results = scan_text_for_secrets("Bearer secret-token-123", source="test.txt")
        assert any(f.pattern == "bearer-token" for f in results)

    def test_detects_openai_style_secret(self):
        results = scan_text_for_secrets("key=sk-abcdefghij123456", source="test.txt")
        assert any(f.pattern == "openai-style-secret" for f in results)


class TestAssertNoSecretScanFindings:
    def test_clean_entries_pass(self):
        assert_no_secret_scan_findings([("file.txt", "clean content")])

    def test_dirty_entries_raise(self):
        try:
            assert_no_secret_scan_findings([("file.txt", "Bearer secret")])
        except SecretScanViolation:
            pass
        else:
            raise AssertionError("Expected SecretScanViolation")
