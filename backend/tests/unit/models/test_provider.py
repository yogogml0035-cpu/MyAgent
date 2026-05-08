from __future__ import annotations

import pytest

from app.config import Settings
from app.models.provider import ModelProviderError, _parse_model_id, create_model


class TestParseModelId:
    def test_valid_provider_model_pair(self):
        provider, name = _parse_model_id("deepseek:deepseek-chat")
        assert provider == "deepseek"
        assert name == "deepseek-chat"

    def test_colon_in_model_name(self):
        provider, name = _parse_model_id("openai:gpt-4o:latest")
        assert provider == "openai"
        assert name == "gpt-4o:latest"


class TestCreateModelErrors:
    def test_missing_api_key_raises_error(self, test_settings):
        with pytest.raises(ModelProviderError, match="API key for provider 'deepseek'"):
            create_model("deepseek:deepseek-chat", test_settings)

    def test_unsupported_provider_raises_error(self, test_settings):
        settings_with_key = Settings(
            task_root=test_settings.task_root,
            workspace_root=test_settings.workspace_root,
            deepseek_api_key="sk-test",
        )
        with pytest.raises(ModelProviderError, match="Unsupported provider 'fake'"):
            create_model("fake:model-name", settings_with_key)

    def test_invalid_format_raises_error(self, test_settings):
        with pytest.raises(ModelProviderError, match="expected format"):
            create_model("no-colon-here", test_settings)

    def test_empty_provider_raises_error(self, test_settings):
        with pytest.raises(ModelProviderError, match="non-empty"):
            create_model(":model-name", test_settings)

    def test_empty_model_name_raises_error(self, test_settings):
        with pytest.raises(ModelProviderError, match="non-empty"):
            create_model("deepseek:", test_settings)
