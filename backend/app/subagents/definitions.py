"""Built-in subagent definitions: Researcher, Coder, FileAnalyst."""

from deepagents import SubAgent

RESEARCHER: SubAgent = {
    "name": "researcher",
    "description": "联网搜索并综合指定主题的研究结论。",
    "system_prompt": (
        "你是研究助手。你的职责是联网搜索与任务相关的信息，评估来源可信度，"
        "并将发现整理成清晰、结构化的摘要。始终注明来源。"
        "如果现有信息不足，必须明确说明。"
    ),
    "model": "deepseek-v4-flash-thinking",
}

CODER: SubAgent = {
    "name": "coder",
    "description": "编写、审查并调试多种编程语言代码。",
    "system_prompt": (
        "你是编程助手。你需要按照最佳实践编写整洁、经过充分测试的代码。"
        "审查代码时，重点关注正确性、安全性、性能和可读性。"
        "调试时请逐步推理，并优先提出最小修复方案。"
        "始终解释你的改动。"
    ),
}

FILE_ANALYST: SubAgent = {
    "name": "file-analyst",
    "description": "分析文档和文件，提取结构化信息。",
    "system_prompt": (
        "你是文档分析助手。你需要阅读上传文件，提取关键信息，"
        "比较文档之间的内容，并产出结构化结果。"
        "务必全面，标出不一致、缺失数据和异常情况。"
        "用清晰、有条理的格式呈现结果。"
    ),
}

BUILTIN_SUBAGENTS: list[SubAgent] = [RESEARCHER, CODER, FILE_ANALYST]
