from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.skills import project
from tests.fakes import InMemoryTaskStorage


def test_get_skills_returns_project_skill_options(tmp_path) -> None:
    settings = Settings(
        task_root=tmp_path / "tasks",
        workspace_root=tmp_path / "tasks",
        skills_dirs=(str(tmp_path / "global-skills"),),
    )
    client = TestClient(create_app(settings, storage=InMemoryTaskStorage(settings.task_root)))

    response = client.get("/api/skills")

    assert response.status_code == 200
    skills = response.json()
    names = {item["name"] for item in skills}
    assert {"code-review", "web-research"}.issubset(names)
    assert all(set(item) == {"name", "description"} for item in skills)


def test_get_skills_does_not_use_settings_skills_dirs(tmp_path, monkeypatch) -> None:
    global_skill_dir = tmp_path / "global-skills" / "private"
    global_skill_dir.mkdir(parents=True)
    (global_skill_dir / "SKILL.md").write_text(
        "---\nname: private-skill\ndescription: Should stay private\n---\n\nBody\n",
        encoding="utf-8",
    )
    settings = Settings(
        task_root=tmp_path / "tasks",
        workspace_root=tmp_path / "tasks",
        skills_dirs=(str(tmp_path / "global-skills"),),
    )
    monkeypatch.setenv("MYAGENT_SKILLS_DIRS", str(tmp_path / "global-skills"))
    client = TestClient(create_app(settings, storage=InMemoryTaskStorage(settings.task_root)))

    response = client.get("/api/skills")

    assert response.status_code == 200
    names = {item["name"] for item in response.json()}
    assert "private-skill" not in names


def test_get_skills_returns_empty_list_when_no_valid_project_skills(
    tmp_path, monkeypatch
) -> None:
    empty_project_skills = tmp_path / "skills"
    empty_project_skills.mkdir()
    monkeypatch.setattr(project, "project_skills_dir", lambda: empty_project_skills)
    settings = Settings(task_root=tmp_path / "tasks", workspace_root=tmp_path / "tasks")
    client = TestClient(create_app(settings, storage=InMemoryTaskStorage(settings.task_root)))

    response = client.get("/api/skills")

    assert response.status_code == 200
    assert response.json() == []
