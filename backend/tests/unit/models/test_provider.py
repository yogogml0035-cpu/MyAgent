from __future__ import annotations

import pytest

from app.config import DEEPSEEK_V4_FLASH_MODEL_ID, DEEPSEEK_V4_FLASH_THINKING_MODEL_ID, Settings
from app.models import provider as provider_module
from app.models.provider import ModelProviderError, create_model


class TestCreateModelErrors:
    def test_missing_api_key_raises_error(self, test_settings):
        with pytest.raises(ModelProviderError, match="DEEPSEEK_API_KEY"):
            create_model(DEEPSEEK_V4_FLASH_MODEL_ID, test_settings)

    def test_unknown_model_raises_error(self, tmp_path):
        settings = Settings(
            task_root=tmp_path / "tasks",
            workspace_root=tmp_path / "tasks",
            deepseek_api_key="sk-test",
        )
        with pytest.raises(ModelProviderError, match="Unsupported model ID"):
            create_model("fake-model", settings)


class TestCreateModelConfiguration:
    @pytest.mark.parametrize(
        ("model_id", "thinking_mode"),
        [
            (DEEPSEEK_V4_FLASH_MODEL_ID, "disabled"),
            (DEEPSEEK_V4_FLASH_THINKING_MODEL_ID, "enabled"),
        ],
    )
    def test_deepseek_ids_map_to_v4_flash_with_expected_thinking_mode(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
        model_id: str,
        thinking_mode: str,
    ):
        captured: dict[str, object] = {}

        class FakeChatDeepSeek:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        monkeypatch.setattr(provider_module, "ChatDeepSeek", FakeChatDeepSeek)
        settings = Settings(
            task_root=tmp_path / "tasks",
            workspace_root=tmp_path / "tasks",
            deepseek_api_key="sk-test",
        )

        create_model(model_id, settings)

        assert captured["model"] == "deepseek-v4-flash"
        assert captured["api_key"] == "sk-test"
        assert captured["api_base"] == "https://api.deepseek.com"
        assert captured["extra_body"] == {"thinking": {"type": thinking_mode}}
