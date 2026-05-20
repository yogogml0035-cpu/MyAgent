"""Project skill discovery REST endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from app.schemas import SkillOption
from app.skills.project import list_project_skill_options

router = APIRouter(prefix="/api", tags=["skills"])


@router.get("/skills", response_model=list[SkillOption])
def get_skills() -> list[dict[str, str]]:
    return list_project_skill_options()
