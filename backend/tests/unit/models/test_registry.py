from __future__ import annotations

from app.config import DEEPSEEK_V4_FLASH_MODEL_ID, DEEPSEEK_V4_FLASH_THINKING_MODEL_ID, Settings
from app.models.registry import (
    get_model_info,
    is_model_available,
    list_available_models,
    validate_model,
)


class TestValidateModel:
    def test_visible_model_id_returns_true(self):
        assert validate_model(DEEPSEEK_V4_FLASH_MODEL_ID) is True

    def test_thinking_model_id_returns_true(self):
        assert validate_model(DEEPSEEK_V4_FLASH_THINKING_MODEL_ID) is True

    def test_invalid_id_returns_false(self):
        assert validate_model("nonexistent-model") is False

    def test_empty_string_returns_false(self):
        assert validate_model("") is False


class TestGetModelInfo:
    def test_existing_model_returns_dict(self):
        info = get_model_info(DEEPSEEK_V4_FLASH_MODEL_ID)
        assert info is not None
        assert info["id"] == DEEPSEEK_V4_FLASH_MODEL_ID
        assert info["provider"] == "deepseek"
        assert info["label"] == "DeepSeek V4 Flash"

    def test_nonexistent_model_returns_none(self):
        assert get_model_info("bogus-model") is None


class TestListAvailableModels:
    def test_returns_all_registered_models(self, test_settings):
        models = list_available_models(test_settings)
        ids = [m["id"] for m in models]
        assert ids == [DEEPSEEK_V4_FLASH_MODEL_ID, DEEPSEEK_V4_FLASH_THINKING_MODEL_ID]

    def test_no_key_means_all_unavailable(self, test_settings):
        models = list_available_models(test_settings)
        assert all(m["available"] is False for m in models)

    def test_key_makes_all_models_available(self, tmp_path):
        settings = Settings(
            task_root=tmp_path / "tasks",
            workspace_root=tmp_path / "tasks",
            deepseek_api_key="sk-test",
        )
        models = list_available_models(settings)
        assert all(m["available"] is True for m in models)


class TestIsModelAvailable:
    def test_unknown_model_is_not_available(self, test_settings):
        assert is_model_available("fake-model", test_settings) is False

    def test_registered_model_without_key_is_not_available(self, test_settings):
        assert is_model_available(DEEPSEEK_V4_FLASH_MODEL_ID, test_settings) is False

    def test_registered_model_with_key_is_available(self, tmp_path):
        settings = Settings(
            task_root=tmp_path / "tasks",
            workspace_root=tmp_path / "tasks",
            deepseek_api_key="sk-test",
        )
        assert is_model_available(DEEPSEEK_V4_FLASH_THINKING_MODEL_ID, settings) is True
