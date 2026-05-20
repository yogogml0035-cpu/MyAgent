from __future__ import annotations

from pathlib import Path

from app.skills import project


def _write_skill_md(directory: Path, name: str, description: str = "A skill") -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "SKILL.md").write_text(
        (
            "---\n"
            f"name: {name}\n"
            f"description: {description}\n"
            "extra_field: should-not-leak\n"
            "---\n\n"
            "Skill body that must not be returned.\n"
        ),
        encoding="utf-8",
    )


def test_project_skills_dir_points_to_backend_skills() -> None:
    skills_dir = project.project_skills_dir()

    assert skills_dir.name == "skills"
    assert skills_dir.parent.name == "backend"


def test_list_project_skill_options_returns_only_name_and_description(
    tmp_path, monkeypatch
) -> None:
    _write_skill_md(tmp_path / "skills" / "example", "example-skill", "Example skill")
    monkeypatch.setattr(project, "project_skills_dir", lambda: tmp_path / "skills")

    options = project.list_project_skill_options()

    assert options == [{"name": "example-skill", "description": "Example skill"}]
    assert set(options[0]) == {"name", "description"}


def test_list_project_skill_options_returns_empty_for_no_valid_skills(
    tmp_path, monkeypatch
) -> None:
    invalid = tmp_path / "skills" / "invalid"
    invalid.mkdir(parents=True)
    (invalid / "SKILL.md").write_text("No frontmatter here\n", encoding="utf-8")
    monkeypatch.setattr(project, "project_skills_dir", lambda: tmp_path / "skills")

    assert project.list_project_skill_options() == []


def test_builtin_project_skills_include_code_review_and_web_research(monkeypatch) -> None:
    monkeypatch.chdir(Path("/"))

    names = project.project_skill_names()

    assert {"code-review", "web-research"}.issubset(names)

def test_validate_project_skill_names_returns_unknown_names(monkeypatch) -> None:
    monkeypatch.setattr(project, "project_skill_names", lambda: {"code-review", "web-research"})

    assert project.validate_project_skill_names(["web-research", "missing"]) == ["missing"]

def test_format_message_with_skill_refs_prefixes_message_in_order() -> None:
    assert (
        project.format_message_with_skill_refs("hello", ["code-review", "web-research"])
        == "[$code-review] [$web-research]\n\nhello"
    )

def test_format_message_with_skill_refs_keeps_messages_without_skills() -> None:
    assert project.format_message_with_skill_refs("hello", []) == "hello"

def test_format_message_with_skill_refs_supports_empty_message() -> None:
    assert project.format_message_with_skill_refs("", ["web-research"]) == "[$web-research]"
