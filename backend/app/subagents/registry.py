"""SubAgent registration and lookup."""

from deepagents import SubAgent

from app.subagents.definitions import BUILTIN_SUBAGENTS

_NAME_INDEX: dict[str, SubAgent] = {s["name"]: s for s in BUILTIN_SUBAGENTS}


def get_builtin_subagents() -> list[SubAgent]:
    """Return the built-in subagent definitions."""
    return list(BUILTIN_SUBAGENTS)


def get_subagent_by_name(name: str) -> SubAgent | None:
    """Look up a subagent by name."""
    return _NAME_INDEX.get(name)
