"""Artifact domain model — immutable metadata records."""
from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass


class ArtifactStatus:
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    PUBLISHED = "published"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class ArtifactType:
    PRESENTATION = "presentation"
    REPORT = "report"
    WALKTHROUGH = "walkthrough"


ALLOWED_TYPES = frozenset(
    {ArtifactType.PRESENTATION, ArtifactType.REPORT, ArtifactType.WALKTHROUGH}
)


def new_artifact_id() -> str:
    return f"art_{secrets.token_hex(6)}"


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ArtifactRecord:
    id: str
    tenant_id: str
    title: str
    description: str
    type: str
    status: str
    created_by: str
    created_at: str
    updated_at: str
    blob_path: str
    version: int = 1
    approved_by: str | None = None
    approved_at: str | None = None
    content_hash: str | None = None
