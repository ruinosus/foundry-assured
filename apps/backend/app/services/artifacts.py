"""Artifact service — generation + governed lifecycle.

Stores are module-level singletons resolved lazily via the factories so tests
can override `_store` / `_content` with in-memory fakes.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from app.artifacts.factory import make_artifact_store, make_content_store
from app.artifacts.models import (
    ALLOWED_TYPES,
    ArtifactRecord,
    ArtifactStatus,
    new_artifact_id,
    sha256_hex,
)
from app.artifacts.validate import validate_html
from app.core.settings import settings

_store = None
_content = None


class Forbidden(Exception):
    """Caller may not act on this artifact (tenant or role mismatch)."""


def _stores():
    global _store, _content
    if _store is None:
        _store = make_artifact_store()
    if _content is None:
        _content = make_content_store()
    return _store, _content


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _actor(user) -> str:
    return getattr(user, "oid", None) or getattr(user, "upn", None) or "unknown"


def _load_scoped(tenant_id: str, artifact_id: str) -> ArtifactRecord:
    store, _ = _stores()
    rec = store.get(tenant_id, artifact_id)
    if rec is None or rec.tenant_id != tenant_id:
        # Never leak existence across tenants.
        raise Forbidden("artifact not found in tenant")
    return rec


def create_draft(*, tenant_id: str, title: str, description: str, type: str,
                 html: str, user) -> ArtifactRecord:
    if type not in ALLOWED_TYPES:
        raise ValueError(f"invalid artifact type: {type}")
    html = validate_html(html, max_bytes=settings.artifact_max_html_bytes)
    store, content = _stores()
    aid = new_artifact_id()
    now = _now()
    blob_path = f"{tenant_id}/{aid}/v1/index.html"
    rec = ArtifactRecord(
        id=aid, tenant_id=tenant_id, title=title, description=description,
        type=type, status=ArtifactStatus.DRAFT, created_by=_actor(user),
        created_at=now, updated_at=now, blob_path=blob_path, version=1,
    )
    content.put(blob_path, html)
    store.put(rec)
    return rec


def list_artifacts(tenant_id: str) -> list[ArtifactRecord]:
    store, _ = _stores()
    return store.list(tenant_id)


def get_artifact(tenant_id: str, artifact_id: str, *, user) -> ArtifactRecord:
    return _load_scoped(tenant_id, artifact_id)


def get_content(tenant_id: str, artifact_id: str, *, user) -> str:
    rec = _load_scoped(tenant_id, artifact_id)
    _, content = _stores()
    html = content.get(rec.blob_path)
    if html is None:
        raise Forbidden("artifact content missing")
    return html


def _save(rec: ArtifactRecord) -> ArtifactRecord:
    store, _ = _stores()
    store.put(rec)
    return rec


def _hash_of(tenant_id: str, artifact_id: str) -> str:
    rec = _load_scoped(tenant_id, artifact_id)
    _, content = _stores()
    return sha256_hex(content.get(rec.blob_path) or "")


def replace_content(tenant_id: str, artifact_id: str, html: str, *, user) -> ArtifactRecord:
    rec = _load_scoped(tenant_id, artifact_id)
    if rec.status != ArtifactStatus.DRAFT:
        raise ValueError("content editable only while draft")
    html = validate_html(html, max_bytes=settings.artifact_max_html_bytes)
    _, content = _stores()
    content.put(rec.blob_path, html)
    return _save(replace(rec, updated_at=_now()))


def request_approval(tenant_id: str, artifact_id: str, *, user) -> ArtifactRecord:
    rec = _load_scoped(tenant_id, artifact_id)
    if rec.status != ArtifactStatus.DRAFT:
        raise ValueError("only a draft can be submitted for approval")
    return _save(replace(rec, status=ArtifactStatus.PENDING_APPROVAL, updated_at=_now()))


def approve(tenant_id: str, artifact_id: str, *, user) -> ArtifactRecord:
    rec = _load_scoped(tenant_id, artifact_id)
    if rec.status != ArtifactStatus.PENDING_APPROVAL:
        raise ValueError("only a pending artifact can be approved")
    now = _now()
    return _save(replace(
        rec, status=ArtifactStatus.PUBLISHED, approved_by=_actor(user),
        approved_at=now, updated_at=now,
        content_hash=_hash_of(tenant_id, artifact_id),
    ))


def reject(tenant_id: str, artifact_id: str, *, user) -> ArtifactRecord:
    rec = _load_scoped(tenant_id, artifact_id)
    if rec.status != ArtifactStatus.PENDING_APPROVAL:
        raise ValueError("only a pending artifact can be rejected")
    return _save(replace(rec, status=ArtifactStatus.DRAFT, updated_at=_now()))


def archive(tenant_id: str, artifact_id: str, *, user) -> ArtifactRecord:
    rec = _load_scoped(tenant_id, artifact_id)
    if rec.status not in (ArtifactStatus.PUBLISHED, ArtifactStatus.DRAFT):
        raise ValueError("only draft/published artifacts can be archived")
    return _save(replace(rec, status=ArtifactStatus.ARCHIVED, updated_at=_now()))
