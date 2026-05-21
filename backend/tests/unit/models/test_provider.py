from __future__ import annotations

from typing import Any, cast

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import SecretStr

from app.config import DEEPSEEK_V4_FLASH_MODEL_ID, DEEPSEEK_V4_FLASH_THINKING_MODEL_ID, Settings
from app.models import provider as provider_module
from app.models.provider import ModelProviderError, create_model


def _thinking_tool_call_messages():
    return [
        HumanMessage(content="请先查询最新招标动态"),
        AIMessage(
            content="我先调用搜索工具确认最新进展。",
            additional_kwargs={"reasoning_content": "需要先拿到最新事实再继续分析。"},
            tool_calls=[
                {
                    "name": "search",
                    "args": {"query": "最新招标动态"},
                    "id": "call-search-1",
                    "type": "tool_call",
                }
            ],
        ),
        ToolMessage(
            content='{"items": ["最新招标动态结果"]}',
            tool_call_id="call-search-1",
        ),
    ]


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
        ("model_id", "thinking_mode", "expected_model_class"),
        [
            (DEEPSEEK_V4_FLASH_MODEL_ID, "disabled", "chat"),
            (DEEPSEEK_V4_FLASH_THINKING_MODEL_ID, "enabled", "thinking"),
        ],
    )
    def test_deepseek_ids_map_to_v4_flash_with_expected_thinking_mode(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
        model_id: str,
        thinking_mode: str,
        expected_model_class: str,
    ):
        captured: dict[str, object] = {}

        class FakeChatDeepSeek:
            def __init__(self, **kwargs):
                captured["model_class"] = "chat"
                captured.update(kwargs)

        class FakeDeepSeekThinkingChatModel:
            def __init__(self, **kwargs):
                captured["model_class"] = "thinking"
                captured.update(kwargs)

        monkeypatch.setattr(provider_module, "ChatDeepSeek", FakeChatDeepSeek)
        monkeypatch.setattr(
            provider_module,
            "DeepSeekThinkingChatModel",
            FakeDeepSeekThinkingChatModel,
        )
        settings = Settings(
            task_root=tmp_path / "tasks",
            workspace_root=tmp_path / "tasks",
            deepseek_api_key="sk-test",
        )

        create_model(model_id, settings)

        assert captured["model_class"] == expected_model_class
        assert captured["model"] == "deepseek-v4-flash"
        api_key = captured["api_key"]
        assert isinstance(api_key, SecretStr)
        assert api_key.get_secret_value() == "sk-test"
        assert captured["api_base"] == "https://api.deepseek.com"
        assert captured["extra_body"] == {"thinking": {"type": thinking_mode}}

    @pytest.mark.parametrize(
        ("model_id", "thinking_expected"),
        [
            (DEEPSEEK_V4_FLASH_MODEL_ID, False),
            (DEEPSEEK_V4_FLASH_THINKING_MODEL_ID, True),
        ],
    )
    def test_create_model_replays_reasoning_only_for_thinking_models(
        self,
        tmp_path,
        model_id: str,
        thinking_expected: bool,
    ):
        settings = Settings(
            task_root=tmp_path / "tasks",
            workspace_root=tmp_path / "tasks",
            deepseek_api_key="sk-test",
        )

        model = create_model(model_id, settings)
        payload = cast(Any, model)._get_request_payload(_thinking_tool_call_messages())

        assistant_message = payload["messages"][1]
        if thinking_expected:
            assert assistant_message["reasoning_content"] == "需要先拿到最新事实再继续分析。"
        else:
            assert "reasoning_content" not in assistant_message
