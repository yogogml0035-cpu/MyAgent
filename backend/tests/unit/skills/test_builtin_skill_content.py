from __future__ import annotations

from pathlib import Path

from app.skills.loader import discover_skills


def _builtin_skills_root() -> Path:
    return Path(__file__).resolve().parents[3] / "skills"


def test_builtin_skill_descriptions_are_localized():
    skills = {
        item["name"]: item
        for item in discover_skills([str(_builtin_skills_root())])
    }

    assert skills["code-review"]["description"].startswith("审查代码质量")
    assert skills["web-research"]["description"].startswith("使用已配置的本地 SearXNG 搜索引擎")


def test_builtin_skill_bodies_are_localized():
    code_review = (_builtin_skills_root() / "code_review" / "SKILL.md").read_text(encoding="utf-8")
    web_research = (_builtin_skills_root() / "web_research" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "# 代码审查技能" in code_review
    assert "使用文件系统工具读取相关代码文件" in code_review
    assert "# 联网研究技能" in web_research
    assert "使用 `searxng_search` 工具做针对性搜索" in web_research
    assert "总搜索调用不超过 5 次" in web_research
    assert "不要使用 `task`/sub-agent 委派" in web_research
    assert "不要生成 Word、PPT、Excel、PDF、HTML 或其他报告产物" in web_research
