"""Migração explícita dos manifestos OKF legados para o perfil de autoria."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .envelope import (
    PROFILE_VERSIONS,
    AuthoringDocument,
    AuthoringInvalid,
    parse_authoring_document,
    serialize_authoring_document,
)

LEGACY_MANIFEST_FORMAT = "okf-v0.2-body-spec"
_LEGACY_TYPES = frozenset({"formflow", "copilot", "policy"})
_FORMFLOW_KEYS = frozenset({"sections", "review", "plan"})


def migrate_legacy_manifest(
    legacy: Mapping[str, Any],
    *,
    source_format: str,
    doc_type: str,
    identifier: str,
    tenant: str,
    area: str,
    revision: str,
    generated_by: str,
    generated_at: str,
    replacement_spec: Mapping[str, Any] | None = None,
    target_profile_version: str = "1",
) -> AuthoringDocument:
    """Cria uma revisão draft; nunca altera nem publica o manifesto de origem."""
    if source_format != LEGACY_MANIFEST_FORMAT:
        raise AuthoringInvalid(f"formato legado incompatível: {source_format!r}")
    if target_profile_version not in PROFILE_VERSIONS:
        raise AuthoringInvalid(
            f"profile_version de destino incompatível: {target_profile_version!r}"
        )
    if doc_type not in _LEGACY_TYPES:
        raise AuthoringInvalid(
            f"{doc_type!r} não possui migração de manifesto; permanece no OKF upstream"
        )

    if replacement_spec is None:
        if doc_type != "formflow":
            raise AuthoringInvalid(
                f"migração de {doc_type!r} exige `replacement_spec` explícito"
            )
        spec = {key: legacy[key] for key in _FORMFLOW_KEYS if key in legacy}
    else:
        spec = dict(replacement_spec)

    title = legacy.get("title")
    description = legacy.get("description")
    metadata = {
        key: value
        for key, value in {"title": title, "description": description}.items()
        if isinstance(value, str) and value.strip()
    }
    heading = title.strip() if isinstance(title, str) and title.strip() else identifier
    document = AuthoringDocument(
        type=doc_type,
        id=identifier,
        profile_version=target_profile_version,
        revision=revision,
        publication_state="draft",
        tenant=tenant,
        area=area,
        generated={"by": generated_by, "at": generated_at},
        resource=str(legacy.get("name", identifier)),
        status="draft",
        spec=spec,
        okf_metadata=metadata,
        body=f"# {heading}",
    )
    return parse_authoring_document(
        serialize_authoring_document(document),
        where=f"migration:{doc_type}/{identifier}",
    )
