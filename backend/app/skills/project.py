"""Project-scoped skill projection for browser-safe API responses."""

from __future__ import annotations

from pathlib import Path

from app.skills.loader import discover_skills


def project_skills_dir() -> Path:
    """Return the repository-local ``backend/skills`` directory."""
    return Path(__file__).resolve().parents[2] / "skills"


def list_project_skill_options() -> list[dict[str, str]]:
    """List project skills with only browser-safe fields."""
    options: list[dict[str, str]] = []
    for skill in discover_skills([str(project_skills_dir())]):
        name = skill.get("name")
        description = skill.get("description")
        if isinstance(name, str) and isinstance(description, str):
            options.append({"name": name, "description": description})
    return options


def project_skill_names() -> set[str]:
    """Return the set of valid project skill names."""
    return {skill["name"] for skill in list_project_skill_options()}

def validate_project_skill_names(names: list[str]) -> list[str]:
    """Return skill names that are not available in the project skill set."""
    valid_names = project_skill_names()
    return [name for name in names if name not in valid_names]

def format_message_with_skill_refs(message: str, skill_names: list[str]) -> str:
    """Prefix a user-visible message with selected skill references."""
    if not skill_names:
        return message
    prefix = " ".join(f"[${name}]" for name in skill_names)
    if not message:
        return prefix
    return f"{prefix}\n\n{message}"
