from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ResourceKind = Literal["upload", "workspace", "artifact", "external"]
ArtifactKind = Literal["html", "markdown", "json", "text"]


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


@dataclass(frozen=True)
class ArtifactRef:
    id: str
    name: str
    artifact_type: ArtifactKind
    uri: str
    run_id: str
    resource: ResourceRef
    size_bytes: int | None = None
    digest: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def build_upload_resource_ref(
    *,
    session_id: str,
    filename: str,
    size_bytes: int | None = None,
    digest: str | None = None,
    media_type: str | None = None,
) -> ResourceRef:
    safe_name = _leaf_name(filename)
    return ResourceRef(
        id=f"upload:{session_id}:{safe_name}",
        kind="upload",
        uri=f"myagent://sessions/{session_id}/resources/{safe_name}",
        name=safe_name,
        media_type=media_type,
        size_bytes=size_bytes,
        digest=digest,
        metadata={"session_id": session_id},
    )


def build_artifact_ref(
    *,
    session_id: str,
    run_id: str,
    name: str,
    artifact_type: ArtifactKind,
    size_bytes: int | None = None,
    digest: str | None = None,
) -> ArtifactRef:
    safe_name = _leaf_name(name)
    uri = f"myagent://sessions/{session_id}/runs/{run_id}/artifacts/{safe_name}"
    resource = ResourceRef(
        id=f"artifact:{session_id}:{run_id}:{safe_name}",
        kind="artifact",
        uri=uri,
        name=safe_name,
        size_bytes=size_bytes,
        digest=digest,
        metadata={"session_id": session_id, "run_id": run_id},
    )
    return ArtifactRef(
        id=resource.id,
        name=safe_name,
        artifact_type=artifact_type,
        uri=uri,
        run_id=run_id,
        resource=resource,
        size_bytes=size_bytes,
        digest=digest,
        metadata={"session_id": session_id, "run_id": run_id},
    )


def resource_ref_payload(ref: ResourceRef) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": ref.id,
        "kind": ref.kind,
        "uri": ref.uri,
    }
    if ref.name is not None:
        payload["name"] = ref.name
    if ref.media_type is not None:
        payload["media_type"] = ref.media_type
    if ref.size_bytes is not None:
        payload["size_bytes"] = ref.size_bytes
    if ref.digest is not None:
        payload["digest"] = ref.digest
    if ref.metadata:
        payload["metadata"] = dict(ref.metadata)
    return payload


def artifact_ref_payload(ref: ArtifactRef) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": ref.id,
        "name": ref.name,
        "type": ref.artifact_type,
        "uri": ref.uri,
        "run_id": ref.run_id,
        "resource_ref": resource_ref_payload(ref.resource),
    }
    if ref.size_bytes is not None:
        payload["size_bytes"] = ref.size_bytes
    if ref.digest is not None:
        payload["digest"] = ref.digest
    if ref.metadata:
        payload["metadata"] = dict(ref.metadata)
    return payload


def _leaf_name(value: str) -> str:
    return value.strip().replace("\\", "/").split("/")[-1]
