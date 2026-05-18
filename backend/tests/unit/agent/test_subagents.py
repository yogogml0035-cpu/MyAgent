from __future__ import annotations

from app.subagents.definitions import BUILTIN_SUBAGENTS, CODER, FILE_ANALYST, RESEARCHER


def test_builtin_subagent_descriptions_are_localized():
    assert RESEARCHER["description"] == "联网搜索并综合指定主题的研究结论。"
    assert CODER["description"] == "编写、审查并调试多种编程语言代码。"
    assert FILE_ANALYST["description"] == "分析文档和文件，提取结构化信息。"


def test_builtin_subagent_system_prompts_are_localized():
    prompts = {subagent["name"]: subagent["system_prompt"] for subagent in BUILTIN_SUBAGENTS}

    assert "你是研究助手" in prompts["researcher"]
    assert "注明来源" in prompts["researcher"]
    assert "You are" not in prompts["researcher"]

    assert "你是编程助手" in prompts["coder"]
    assert "最小修复方案" in prompts["coder"]
    assert "You are" not in prompts["coder"]

    assert "你是文档分析助手" in prompts["file-analyst"]
    assert "结构化结果" in prompts["file-analyst"]
    assert "You are" not in prompts["file-analyst"]
