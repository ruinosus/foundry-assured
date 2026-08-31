"""Payloads de evidência criados uma vez no container imutável da ADR-023."""

from __future__ import annotations

import json
import re
from typing import Any

from app.modules.audit.internal.trail import trail

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", re.ASCII)
_PREFIX = "mcp-snapshots/"


class EvidenceExists(ValueError):
    """A evidência já existe e não pode ser sobrescrita."""


class InvalidEvidence(ValueError):
    """Identidade ou payload inadequado para persistência."""


class InMemoryEvidenceStore:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str], bytes] = {}

    def create(self, scope: str, evidence_id: str, body: bytes) -> None:
        key = (scope, evidence_id)
        if key in self._items:
            raise EvidenceExists(f"evidência {evidence_id!r} já existe")
        self._items[key] = body

    def read(self, scope: str, evidence_id: str) -> bytes | None:
        return self._items.get((scope, evidence_id))


class BlobEvidenceStore:
    def __init__(self, container) -> None:
        self._container = container

    def _blob(self, scope: str, evidence_id: str):
        return self._container.get_blob_client(f"{_PREFIX}{scope}/{evidence_id}.json")

    def create(self, scope: str, evidence_id: str, body: bytes) -> None:
        from azure.core import MatchConditions
        from azure.core.exceptions import ResourceExistsError, ResourceModifiedError
        from azure.storage.blob import ContentSettings

        try:
            self._blob(scope, evidence_id).upload_blob(
                body,
                match_condition=MatchConditions.IfMissing,
                content_settings=ContentSettings(content_type="application/json"),
            )
        except (ResourceExistsError, ResourceModifiedError) as exc:
            raise EvidenceExists(f"evidência {evidence_id!r} já existe") from exc

    def read(self, scope: str, evidence_id: str) -> bytes | None:
        from azure.core.exceptions import ResourceNotFoundError

        try:
            return self._blob(scope, evidence_id).download_blob().readall()
        except ResourceNotFoundError:
            return None


_MEMORY_STORES: dict[int, InMemoryEvidenceStore] = {}
_BLOB_STORES: dict[int, BlobEvidenceStore] = {}


def _store():
    current_trail = trail()
    container = getattr(current_trail, "_container", None)
    key = id(current_trail)
    if container is None:
        return _MEMORY_STORES.setdefault(key, InMemoryEvidenceStore())
    return _BLOB_STORES.setdefault(key, BlobEvidenceStore(container))


def _validated_id(evidence_id: str) -> str:
    if not isinstance(evidence_id, str) or not _ID.fullmatch(evidence_id):
        raise InvalidEvidence("identidade de evidência inválida")
    return evidence_id


def write_evidence(
    evidence_id: str,
    payload: dict[str, Any],
    *,
    scope: str = "global",
    store=None,
) -> dict:
    """Cria JSON uma única vez; o chamador deve entregar conteúdo já sanitizado."""
    _validated_id(evidence_id)
    _validated_id(scope)
    if not isinstance(payload, dict):
        raise InvalidEvidence("payload de evidência deve ser um objeto")
    body = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    (store or _store()).create(scope, evidence_id, body)
    return {"id": evidence_id, "bytes": len(body), "written": True}


def read_evidence(evidence_id: str, *, scope: str = "global", store=None) -> dict | None:
    _validated_id(evidence_id)
    _validated_id(scope)
    body = (store or _store()).read(scope, evidence_id)
    return json.loads(body.decode("utf-8")) if body is not None else None
