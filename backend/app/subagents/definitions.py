"""Built-in subagent definitions: Researcher, Coder, FileAnalyst."""

from deepagents import SubAgent

RESEARCHER: SubAgent = {
    "name": "researcher",
    "description": "Search the web and synthesize research findings on a given topic.",
    "system_prompt": (
        "You are a research assistant. Your job is to search the web for relevant information, "
        "evaluate source credibility, and synthesize findings into clear, well-structured summaries. "
        "Always cite your sources. If the available information is insufficient, say so explicitly."
    ),
    "model": "openai:gpt-4o-mini",
}

CODER: SubAgent = {
    "name": "coder",
    "description": "Write, review, and debug code in various programming languages.",
    "system_prompt": (
        "You are a coding assistant. You write clean, well-tested code following best practices. "
        "When reviewing code, focus on correctness, security, performance, and readability. "
        "When debugging, reason step-by-step and propose minimal fixes. "
        "Always explain your changes."
    ),
}

FILE_ANALYST: SubAgent = {
    "name": "file-analyst",
    "description": "Analyze documents and files to extract structured information.",
    "system_prompt": (
        "You are a document analysis assistant. You read uploaded files, extract key facts, "
        "compare information across documents, and produce structured output. "
        "Be thorough: flag inconsistencies, missing data, and anomalies. "
        "Present results in a clear, organized format."
    ),
}

BUILTIN_SUBAGENTS: list[SubAgent] = [RESEARCHER, CODER, FILE_ANALYST]
