"""Skill registry: indexed skills from configured directories."""

from app.skills.loader import discover_skills


class SkillRegistry:
    """Discover and index SKILL.md files from configured directories."""

    def __init__(self, skills_dirs: list[str]) -> None:
        self._skills = discover_skills(skills_dirs)
        self._by_name: dict[str, dict] = {s["name"]: s for s in self._skills}

    def list_skills(self) -> list[dict]:
        """Return all discovered skills with name, description, path."""
        return list(self._skills)

    def get_skill(self, name: str) -> dict | None:
        """Look up a skill by name."""
        return self._by_name.get(name)

    def get_skills_sources(self) -> list[str]:
        """Return skill directory paths for ``create_deep_agent(skills=...)``."""
        return [s["path"] for s in self._skills]
