"""Normalização pura de um rascunho em proposta OKF multi-documento."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from app.modules.okf.public import (
    AuthoringDocument,
    AuthoringInvalid,
    ChangeDecision,
    ChangeEvidence,
    ChangeGap,
    ChangeOperation,
    OkfChangeSet,
    parse_authoring_document,
    serialize_authoring_document,
)

_SLUG_PARTS = re.compile(r"[^a-z0-9]+")
_VERSION = re.compile(r"^[1-9]\d*(?:\.\d+){0,2}$", re.ASCII)
_SENSITIVE = re.compile(
    r"(?:bearer\s+\S+|AccountKey=\S+|SharedAccessSignature=\S+)", re.IGNORECASE
)


def _slug(value: Any, fallback: str) -> str:
    normalized = _SLUG_PARTS.sub("-", str(value or "").lower()).strip("-")
    return (normalized or fallback)[:63].rstrip("-")


def _safe_text(value: Any, fallback: str, limit: int = 512) -> str:
    text = _SENSITIVE.sub("[REDACTED]", str(value or "").strip())
    return (text or fallback)[:limit]


def _document(
    doc_type: str,
    identifier: str,
    tenant_id: str,
    area_id: str,
    spec: dict[str, Any],
    body: str,
    *,
    resource: str | None = None,
) -> AuthoringDocument:
    return AuthoringDocument(
        type=doc_type,
        id=identifier,
        profile_version="1",
        revision="1",
        publication_state="proposed",
        tenant=tenant_id,
        area=area_id,
        generated={"by": "process:builder", "at": datetime.now(UTC).isoformat()},
        resource=resource,
        status="draft",
        spec=spec,
        body=body,
    )


def _selected_agent(draft: Mapping[str, Any], items: list[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    agents = {
        str(item.get("id") or item.get("name")): item
        for item in items
        if item.get("kind") == "agent" and item.get("selectable") is True
    }
    candidates = [
        str(item.get("name") or "")
        for item in draft.get("reuse", [])
        if isinstance(item, Mapping)
    ]
    candidates.append(str(draft.get("name") or ""))
    for candidate in candidates:
        if candidate in agents:
            return agents[candidate]
        match = next((item for item in agents.values() if item.get("name") == candidate), None)
        if match is not None:
            return match
    return None


def build_changeset_proposal(
    draft: Mapping[str, Any],
    catalog: Mapping[str, Any],
    *,
    tenant_id: str,
    area_id: str,
    actor_id: str,
) -> dict[str, Any]:
    """Cria uma proposta inerte ou uma lacuna bloqueadora quando não há implementação real."""
    snapshot = catalog.get("snapshot")
    items = catalog.get("items")
    if not isinstance(snapshot, Mapping) or not isinstance(snapshot.get("id"), str):
        raise ValueError("O snapshot factual do catálogo é inválido.")  # noqa: TRY004
    if not isinstance(items, list) or any(not isinstance(item, Mapping) for item in items):
        raise ValueError("Os itens do catálogo são inválidos.")

    selected = _selected_agent(draft, items)
    version = selected.get("version") if selected is not None else None
    if selected is None or not isinstance(version, str) or not _VERSION.fullmatch(version):
        return {
            "snapshot": dict(snapshot),
            "partial": bool(catalog.get("partial")),
            "proposal": None,
            "gaps": [
                {
                    "capability": "agent-implementation",
                    "reason": "Nenhum agente publicado e versionado do snapshot atende à necessidade.",
                    "status": "missing",
                }
            ],
            "published": False,
        }

    agent_name = str(selected.get("id") or selected.get("name"))
    base_name = _slug(draft.get("name") or agent_name, "agent-proposal")
    binding_id = _slug(f"{base_name}-binding", "agent-binding")
    usecase_id = _slug(f"{base_name}-usecase", "agent-usecase")
    rationale = _safe_text(
        draft.get("rationale") or draft.get("description"),
        f"Reutilizar o agente publicado {agent_name}.",
    )
    source = f"catalog:agent/{agent_name}@{version}"

    proposer = _document(
        "copilot",
        "builder",
        tenant_id,
        area_id,
        {
            "writes": [
                {"type": "agent-binding", "operations": ["create"]},
                {"type": "usecase", "operations": ["create"]},
            ],
            "cannotWrite": [{"type": "policy"}, {"type": "connection"}],
        },
        "Builder de propostas OKF. Não publica recursos.",
    )
    binding = _document(
        "agent-binding",
        binding_id,
        tenant_id,
        area_id,
        {"agent": {"name": agent_name, "version": version}},
        _safe_text(draft.get("description"), f"Binding para {agent_name}."),
        resource=f"foundry:agent/{agent_name}@{version}",
    )
    reference = {"type": "agent-binding", "id": binding_id, "revision": "1"}
    usecase = _document(
        "usecase",
        usecase_id,
        tenant_id,
        area_id,
        {
            "requires": [reference],
            "targets": [reference],
            "approval": {"required": True, "role": "Approver"},
            "cost": {"kind": "unknown"},
            "citation": "required" if draft.get("knowledge") else "optional",
            "gaps": [],
        },
        rationale,
    )
    changeset = OkfChangeSet(
        id=_slug(f"{base_name}-proposal", "builder-proposal"),
        base_version=str(snapshot["id"]),
        proposer=proposer,
        justification=rationale,
        operations=(
            ChangeOperation(
                id=f"create-{binding_id}",
                operation="create",
                document=binding,
                justification=f"Seleciona a implementação publicada {agent_name}@{version}.",
                evidence=(ChangeEvidence("spec.agent", source),),
            ),
            ChangeOperation(
                id=f"create-{usecase_id}",
                operation="create",
                document=usecase,
                justification=rationale,
                depends_on=(f"create-{binding_id}",),
                evidence=(
                    ChangeEvidence("spec.requires", f"changeset:create-{binding_id}"),
                    ChangeEvidence("spec.targets", f"changeset:create-{binding_id}"),
                    ChangeEvidence("spec.approval", "entra:app-role/Approver"),
                    ChangeEvidence("spec.cost", "catalog:cost-unavailable"),
                    ChangeEvidence("spec.citation", "builder:grounding-selection"),
                    ChangeEvidence("spec.gaps", "builder:catalog-analysis"),
                ),
            ),
        ),
        gaps=tuple(
            ChangeGap(str(gap.get("kind") or "catalog"), "Fonte do catálogo indisponível.")
            for gap in catalog.get("gaps", [])
            if isinstance(gap, Mapping)
        ),
    )
    structured = changeset.to_dict(current_version=str(snapshot["id"]))
    documents = {operation.id: serialize_authoring_document(operation.document) for operation in changeset.operations}
    for operation in structured["operations"]:
        operation["document_type"] = operation["document"]["frontmatter"]["type"]
        operation["document"] = documents[operation["id"]]
        operation["gaps"] = []
        operation["decision"] = "pending"
    return {
        "snapshot": dict(snapshot),
        "partial": bool(catalog.get("partial")),
        "proposal": structured,
        "gaps": structured["gaps"],
        "published": False,
    }


def _operation_evidence(
    document: AuthoringDocument,
    items: list[Mapping[str, Any]],
    *,
    edited: bool,
) -> tuple[ChangeEvidence, ...]:
    if edited:
        return (ChangeEvidence("spec", "human:review"),)
    if document.type == "agent-binding":
        agent = document.spec["agent"]
        match = next(
            (
                item
                for item in items
                if item.get("kind") == "agent"
                and item.get("selectable") is True
                and str(item.get("id") or item.get("name")) == agent["name"]
                and str(item.get("version")) == agent["version"]
            ),
            None,
        )
        if match is None:
            raise AuthoringInvalid(
                f"agent-binding {document.id}: implementação não existe no snapshot"
            )
        return (
            ChangeEvidence(
                "spec.agent", f"catalog:agent/{agent['name']}@{agent['version']}"
            ),
        )
    if document.type == "usecase":
        return (
            ChangeEvidence("spec.requires", "changeset:review"),
            ChangeEvidence("spec.targets", "changeset:review"),
            ChangeEvidence("spec.approval", "entra:app-role/Approver"),
            ChangeEvidence("spec.cost", "catalog:cost-unavailable"),
            ChangeEvidence("spec.citation", "builder:grounding-selection"),
            ChangeEvidence("spec.gaps", "builder:catalog-analysis"),
        )
    raise AuthoringInvalid(f"operation.document: tipo não autorizado pelo Builder: {document.type}")


def review_changeset_proposal(
    proposal: Mapping[str, Any],
    decisions: list[Mapping[str, Any]],
    catalog: Mapping[str, Any],
    *,
    tenant_id: str,
    area_id: str,
) -> dict[str, Any]:
    """Reconstrói, revisa e confirma no servidor o conjunto exato escolhido pelo Author."""
    snapshot = catalog.get("snapshot")
    items = catalog.get("items")
    if not isinstance(snapshot, Mapping) or proposal.get("base_version") != snapshot.get("id"):
        raise AuthoringInvalid("SNAPSHOT_STALE")
    if not isinstance(items, list) or any(not isinstance(item, Mapping) for item in items):
        raise AuthoringInvalid("CATALOG_ITEMS_INVALID")
    raw_operations = proposal.get("operations")
    if not isinstance(raw_operations, list) or not raw_operations:
        raise AuthoringInvalid("proposal.operations: exige operações")
    by_decision = {
        str(decision.get("operation_id")): decision
        for decision in decisions
        if isinstance(decision, Mapping)
    }
    if len(by_decision) != len(decisions):
        raise AuthoringInvalid("proposal.review: decisões duplicadas não são permitidas")
    operation_ids = {
        str(operation.get("id"))
        for operation in raw_operations
        if isinstance(operation, Mapping)
    }
    if set(by_decision) != operation_ids:
        raise AuthoringInvalid("proposal.review: exige decisão explícita para cada operação")

    proposer = _document(
        "copilot",
        "builder",
        tenant_id,
        area_id,
        {
            "writes": [
                {"type": "agent-binding", "operations": ["create"]},
                {"type": "usecase", "operations": ["create"]},
            ],
            "cannotWrite": [{"type": "policy"}, {"type": "connection"}],
        },
        "Builder de propostas OKF. Não publica recursos.",
    )
    operations: list[ChangeOperation] = []
    review: list[ChangeDecision] = []
    for raw in raw_operations:
        if not isinstance(raw, Mapping):
            raise AuthoringInvalid("proposal.operations: operação inválida")
        operation_id = str(raw.get("id") or "")
        decision = by_decision[operation_id]
        original = parse_authoring_document(str(raw.get("document") or ""))
        if (original.tenant, original.area) != (tenant_id, area_id):
            raise AuthoringInvalid(f"operation {operation_id}: documento fora do tenant/área")
        operations.append(
            ChangeOperation(
                id=operation_id,
                operation=str(raw.get("operation") or ""),
                document=original,
                justification=_safe_text(
                    raw.get("justification"), "Mudança proposta pelo Builder."
                ),
                base_revision=str(raw["base_revision"]) if raw.get("base_revision") else None,
                depends_on=tuple(str(value) for value in (raw.get("depends_on") or [])),
                evidence=_operation_evidence(original, items, edited=False),
            )
        )
        choice = str(decision.get("decision") or "")
        if choice == "edit":
            edited = parse_authoring_document(str(decision.get("edited_document") or ""))
            if (edited.tenant, edited.area) != (tenant_id, area_id):
                raise AuthoringInvalid(f"operation {operation_id}: edição fora do tenant/área")
            _operation_evidence(edited, items, edited=False)
            review.append(
                ChangeDecision(
                    operation_id,
                    "edit",
                    edited,
                    _operation_evidence(edited, items, edited=True),
                )
            )
        else:
            review.append(ChangeDecision(operation_id, choice))

    changeset = OkfChangeSet(
        id=_slug(proposal.get("id"), "builder-proposal"),
        base_version=str(snapshot["id"]),
        proposer=proposer,
        justification=_safe_text(
            proposal.get("justification"), "Proposta revisada pelo Author."
        ),
        operations=tuple(operations),
        gaps=tuple(
            ChangeGap(str(gap.get("kind") or "catalog"), "Fonte do catálogo indisponível.")
            for gap in catalog.get("gaps", [])
            if isinstance(gap, Mapping)
        ),
    )
    reviewed = changeset.review(review, current_version=str(snapshot["id"]))
    if reviewed is None:
        raise AuthoringInvalid("proposal.review: nenhuma operação foi mantida")
    confirmed = reviewed.confirm(current_version=str(snapshot["id"]))
    structured = reviewed.changeset.to_dict(current_version=str(snapshot["id"]))
    documents = {
        operation.id: serialize_authoring_document(operation.document)
        for operation in reviewed.changeset.operations
    }
    for operation in structured["operations"]:
        operation["document_type"] = operation["document"]["frontmatter"]["type"]
        operation["document"] = documents[operation["id"]]
    return {**structured, "confirmation_digest": confirmed.digest}
