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
