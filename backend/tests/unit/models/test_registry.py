from __future__ import annotations

from app.config import Settings
from app.models.registry import (
    get_model_info,
    list_available_models,
    validate_model,
)


class TestValidateModel:
    def test_valid_id_returns_true(self):
        assert validate_model("deepseek:deepseek-chat") is True

    def test_another_valid_id(self):
        assert validate_model("openai:gpt-4o") is True

    def test_invalid_id_returns_false(self):
        assert validate_model("nonexistent:model") is False

    def test_empty_string_returns_false(self):
        assert validate_model("") is False


class TestGetModelInfo:
    def test_existing_model_returns_dict(self):
        info = get_model_info("deepseek:deepseek-chat")
        assert info is not None
        assert info["id"] == "deepseek:deepseek-chat"
        assert info["provider"] == "deepseek"
        assert info["label"] == "DeepSeek Chat"

    def test_nonexistent_model_returns_none(self):
        assert get_model_info("bogus:model") is None


class TestListAvailableModels:
    def test_returns_all_registered(self, test_settings):
        models = list_available_models(test_settings)
        ids = [m["id"] for m in models]
        assert "deepseek:deepseek-chat" in ids
        assert "openai:gpt-4o" in ids
        assert "anthropic:claude-sonnet-4-20250514" in ids

    def test_no_keys_means_all_unavailable(self, test_settings):
        models = list_available_models(test_settings)
        assert all(m["available"] is False for m in models)

    def test_key_makes_model_available(self, tmp_path):
        settings = Settings(
            task_root=tmp_path / "tasks",
            workspace_root=tmp_path / "tasks",
            deepseek_api_key="sk-test",
        )
        models = list_available_models(settings)
        deepseek_models = [m for m in models if m["provider"] == "deepseek"]
        assert all(m["available"] is True for m in deepseek_models)

    def test_entry_has_expected_fields(self, test_settings):
        models = list_available_models(test_settings)
        for entry in models:
            assert "id" in entry
            assert "label" in entry
            assert "provider" in entry
            assert "available" in entry
