from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Literal, Protocol, runtime_checkable

CredentialKind = Literal["api_key", "oauth_token", "access_token", "service_account", "other"]

_SAFE_REF_PATTERN = re.compile(r"[^A-Za-z0-9_.:-]+")


@dataclass(frozen=True)
class CredentialRef:
    id: str
    label: str
    kind: CredentialKind
    fingerprint: str


@runtime_checkable
class SecretVault(Protocol):
    def resolve(self, ref: CredentialRef) -> str:
        ...


def build_credential_ref(
    *,
    provider: str,
    name: str,
    kind: CredentialKind = "api_key",
    secret: str | None = None,
) -> CredentialRef:
    provider_id = _safe_ref_segment(provider or "provider")
    name_id = _safe_ref_segment(name or "credential")
    label = f"{provider_id}:{name_id}"
    fingerprint_source = secret if secret is not None else label
    fingerprint = "sha256:" + hashlib.sha256(
        fingerprint_source.encode("utf-8")
    ).hexdigest()[:16]
    return CredentialRef(
        id=f"credential:{label}",
        label=label,
        kind=kind,
        fingerprint=fingerprint,
    )


def credential_ref_payload(ref: CredentialRef) -> dict[str, Any]:
    return {
        "id": ref.id,
        "label": ref.label,
        "fingerprint": ref.fingerprint,
    }


class InMemorySecretVault(SecretVault):
    """Test-only vault boundary; production code should use backend-owned config."""

    def __init__(self, secrets: dict[str, str]) -> None:
        self._secrets = dict(secrets)

    def resolve(self, ref: CredentialRef) -> str:
        return self._secrets[ref.id]


def _safe_ref_segment(value: str) -> str:
    normalized = _SAFE_REF_PATTERN.sub("-", value.strip()).strip("-._:")
    return normalized[:80] or "credential"
