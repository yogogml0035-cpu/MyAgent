"""SKILL.md discovery and YAML frontmatter parsing."""

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_YAML_KEY_RE = re.compile(r"^(\w+):\s*(.+)$", re.MULTILINE)


def _parse_frontmatter(text: str) -> dict[str, str]:
    """Extract YAML key-value pairs from ``---``-delimited frontmatter."""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}
    body = m.group(1)
    result: dict[str, str] = {}
    for line_match in _YAML_KEY_RE.finditer(body):
        result[line_match.group(1)] = line_match.group(2).strip().strip('"').strip("'")
    return result


def discover_skills(skills_dirs: list[str]) -> list[dict]:
    """Scan *skills_dirs* for subdirectories containing ``SKILL.md``.

    Returns a list of ``{"name": str, "description": str, "path": str}`` dicts.
    Malformed or missing files are skipped with a warning.
    """
    skills: list[dict] = []
    seen_names: set[str] = set()

    for raw_dir in skills_dirs:
        skills_root = Path(raw_dir)
        if not skills_root.is_dir():
            continue
        for child in sorted(skills_root.iterdir()):
            if not child.is_dir():
                continue
            skill_file = child / "SKILL.md"
            if not skill_file.is_file():
                continue
            try:
                text = skill_file.read_text(encoding="utf-8")
            except OSError:
                logger.warning("Cannot read %s, skipping", skill_file)
                continue
            meta = _parse_frontmatter(text)
            name = meta.get("name", "")
            description = meta.get("description", "")
            if not name:
                logger.warning("SKILL.md in %s has no 'name' in frontmatter, skipping", child)
                continue
            if name in seen_names:
                logger.warning("Duplicate skill name %s, skipping %s", name, child)
                continue
            seen_names.add(name)
            skills.append({"name": name, "description": description, "path": str(skill_file)})

    return skills
