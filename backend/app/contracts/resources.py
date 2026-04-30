from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ResourceKind = Literal["upload", "workspace", "artifact", "external"]


@dataclass(frozen=True)
class ResourceRef:
    id: str
    kind: ResourceKind
    uri: str
    name: str | None = None
    media_type: str | None = None
    size_bytes: int | None = None
    digest: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
