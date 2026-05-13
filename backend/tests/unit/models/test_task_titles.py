from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage

from app.config import Settings
from app.task_titles import (
    fallback_title_from_message,
    generate_task_title,
    sanitize_generated_title,
)


def test_sanitize_generated_title_keeps_first_line_and_ten_chars():
    title = sanitize_generated_title("标题：招标文件差异分析\n解释文本", "请分析招标文件")

    assert title == "招标文件差异分析"
    assert len(title) == 8


def test_sanitize_generated_title_falls_back_for_blank_output():
    assert sanitize_generated_title("   ", "  请帮我总结用户消息并命名  ") == "请帮我总结用户消息并"


def test_fallback_title_uses_first_ten_visible_characters():
    assert fallback_title_from_message("  多行\n空白\t会压缩再命名  ") == "多行 空白 会压缩再"
    assert fallback_title_from_message("   ") == "新对话"


@pytest.mark.asyncio
async def test_generate_task_title_uses_configured_model(monkeypatch, tmp_path):
    calls = {}

    class FakeModel:
        async def ainvoke(self, messages):
            calls["messages"] = messages
            return AIMessage(content="标题：投标文件分析报告")

    def fake_create_model(model, *, settings, temperature):
        calls["model"] = model
        calls["settings"] = settings
        calls["temperature"] = temperature
        return FakeModel()

    monkeypatch.setattr("app.task_titles.create_model", fake_create_model)
    settings = Settings(
        task_root=tmp_path / "tasks",
        workspace_root=tmp_path / "tasks",
        deepseek_api_key="sk-test",
    )

    title = await generate_task_title("请分析这批投标文件", "deepseek:deepseek-chat", settings)

    assert title == "投标文件分析报告"
    assert calls["model"] == "deepseek:deepseek-chat"
    assert calls["temperature"] == 0.0
    assert len(calls["messages"]) == 2
