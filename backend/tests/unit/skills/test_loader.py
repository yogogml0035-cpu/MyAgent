from __future__ import annotations

from pathlib import Path

from app.skills.loader import discover_skills


def _write_skill_md(directory: Path, name: str, description: str = "A skill") -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\nSkill body.\n",
        encoding="utf-8",
    )


class TestDiscoverSkills:
    def test_finds_skill_md_files(self, tmp_path):
        skills_dir = tmp_path / "skills"
        _write_skill_md(skills_dir / "my-skill", "my-skill", "Does stuff")

        results = discover_skills([str(skills_dir)])
        assert len(results) == 1
        assert results[0]["name"] == "my-skill"
        assert results[0]["description"] == "Does stuff"
        assert "SKILL.md" in results[0]["path"]

    def test_empty_dir_returns_empty(self, tmp_path):
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        results = discover_skills([str(empty_dir)])
        assert results == []

    def test_nonexistent_dir_returns_empty(self, tmp_path):
        results = discover_skills([str(tmp_path / "nope")])
        assert results == []

    def test_malformed_skill_md_skipped(self, tmp_path):
        skills_dir = tmp_path / "skills"
        bad_dir = skills_dir / "bad-skill"
        bad_dir.mkdir(parents=True)
        (bad_dir / "SKILL.md").write_text("No frontmatter here\n", encoding="utf-8")

        results = discover_skills([str(skills_dir)])
        assert results == []

    def test_duplicate_name_keeps_first(self, tmp_path):
        skills_dir = tmp_path / "skills"
        _write_skill_md(skills_dir / "skill-a", "dup", "First")
        _write_skill_md(skills_dir / "skill-b", "dup", "Second")

        results = discover_skills([str(skills_dir)])
        assert len(results) == 1
        assert results[0]["description"] == "First"

    def test_file_instead_of_dir_skipped(self, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "not-a-dir.md").write_text("hello", encoding="utf-8")

        results = discover_skills([str(skills_dir)])
        assert results == []

    def test_multiple_dirs_scanned(self, tmp_path):
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        _write_skill_md(dir_a / "s1", "skill-one", "From A")
        _write_skill_md(dir_b / "s2", "skill-two", "From B")

        results = discover_skills([str(dir_a), str(dir_b)])
        assert len(results) == 2
        names = [r["name"] for r in results]
        assert "skill-one" in names
        assert "skill-two" in names
