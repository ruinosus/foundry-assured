"""Proposta multi-documento OKF sem publicação ou efeitos colaterais."""

from __future__ import annotations

import sqlite3
import sys
import tempfile
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.modules.okf.public import (
    AuthoringInvalid,
    ChangeDecision,
    ChangeEvidence,
    ChangeGap,
    ChangeOperation,
    OkfChangeSet,
    parse_authoring_document,
    serialize_authoring_document,
)
from app.modules.proposer.public import (
    build_changeset_proposal,
    review_changeset_proposal,
)


class _PostgresCursor:
    def __init__(self, cursor) -> None:
        self._cursor = cursor

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount

    def execute(self, statement: str, parameters=()):
        self._cursor.execute(statement.replace("%s", "?"), parameters)
        return self

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()


class _PostgresConnection:
    """DB-API PostgreSQL fake: exercises that adapter's SQL contract over SQLite."""

    def __init__(self, path: Path) -> None:
        self._connection = sqlite3.connect(path)
        self._connection.row_factory = sqlite3.Row

    def cursor(self) -> _PostgresCursor:
        return _PostgresCursor(self._connection.cursor())

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        self._connection.close()


def _document(
    doc_type: str,
    identifier: str,
    spec: dict[str, Any],
    *,
    writes: list[dict[str, Any]] | None = None,
    revision: str = "1",
    publication_state: str = "proposed",
    supersedes: dict[str, str] | None = None,
    area: str = "support",
):
    actual_spec = (
        {"writes": writes, "cannotWrite": [{"type": "policy"}]}
        if doc_type == "copilot"
        else spec
    )
    profile = {
        "profile_version": "1",
        "id": identifier,
        "revision": revision,
        "publication_state": publication_state,
        "tenant": "tenant-a",
        "area": area,
        "spec": actual_spec,
    }
    if supersedes is not None:
        profile["supersedes"] = supersedes
    header = {
        "type": doc_type,
        "status": {
            "active": "stable",
            "deprecated": "deprecated",
        }.get(publication_state, "draft"),
        "generated": {"by": "process:builder", "at": "2026-08-31T12:00:00Z"},
        "x-foundry-authoring": profile,
    }
    return parse_authoring_document(
        f"---\n{yaml.safe_dump(header, sort_keys=False).rstrip()}\n---\n\n# {identifier}\n"
    )


def _valid_changeset() -> OkfChangeSet:
    proposer = _document(
        "copilot",
        "builder",
        {},
        writes=[
            {"type": "agent-binding", "operations": ["create", "revise", "deprecate"]},
            {"type": "mcp-binding", "operations": ["create"]},
            {"type": "usecase", "operations": ["create"]},
        ],
    )
    agent = _document(
        "agent-binding",
        "ticket-agent",
        {"agent": {"name": "ticket-agent", "version": "1"}},
    )
    mcp = _document(
        "mcp-binding",
        "ticket-mcp",
        {
            "toolbox": {"name": "ticket-tools", "version": "1"},
            "tools": ["create_ticket"],
            "reviewedSnapshot": {"id": "msnap_0123456789abcdef", "hash": "a" * 64},
        },
    )
    usecase = _document(
        "usecase",
        "ticket-create",
        {
            "requires": [
                {"type": "agent-binding", "id": "ticket-agent", "revision": "1"},
                {"type": "mcp-binding", "id": "ticket-mcp", "revision": "1"},
            ],
            "targets": [{"type": "agent-binding", "id": "ticket-agent", "revision": "1"}],
            "approval": {"required": True, "role": "Approver"},
            "cost": {"kind": "unknown"},
            "citation": "required",
            "gaps": [],
        },
    )
    return OkfChangeSet(
        id="ticket-proposal",
        base_version="catalog-42",
        proposer=proposer,
        justification="Criar o fluxo de tickets com capacidades reais.",
        gaps=(ChangeGap("duplicate-ticket-check", "Implementação ainda não registrada."),),
        operations=(
            ChangeOperation(
                "create-agent",
                "create",
                agent,
                "Seleciona o agente publicado.",
                evidence=(ChangeEvidence("spec.agent", "foundry:agent/ticket-agent@1"),),
            ),
            ChangeOperation(
                "create-mcp",
                "create",
                mcp,
                "Seleciona o toolbox publicado.",
                evidence=(
                    ChangeEvidence("spec.toolbox", "foundry:toolbox/ticket-tools@1"),
                    ChangeEvidence("spec.tools", "mcp-snapshot:msnap_0123456789abcdef"),
                    ChangeEvidence(
                        "spec.reviewedSnapshot", "mcp-snapshot:msnap_0123456789abcdef"
                    ),
                ),
            ),
            ChangeOperation(
                "create-usecase",
                "create",
                usecase,
                "Compõe consulta e criação de ticket.",
                depends_on=("create-agent", "create-mcp"),
                evidence=(
                    ChangeEvidence("spec.requires", "catalog:ticket-capabilities"),
                    ChangeEvidence("spec.targets", "catalog:ticket-capabilities"),
                    ChangeEvidence("spec.approval", "policy:tool-approval"),
                    ChangeEvidence("spec.cost", "catalog:ticket-capabilities"),
                    ChangeEvidence("spec.citation", "policy:assurance"),
                    ChangeEvidence("spec.gaps", "builder:analysis"),
                ),
            ),
        ),
    )


def main() -> int:
    failures: list[str] = []
    current_version = "catalog-42"

    def check(name: str, operation, *, fails: bool = False) -> None:
        if not callable(operation):
            passed = bool(operation) is not fails
            print(f"  {'✓' if passed else '✗'} {name}")
            if not passed:
                failures.append(name)
            return
        try:
            operation()
        except AuthoringInvalid:
            passed = fails
        else:
            passed = not fails
        print(f"  {'✓' if passed else '✗'} {name}")
        if not passed:
            failures.append(name)

    changeset = _valid_changeset()
    check(
        "multi-document proposal resolves intra-set references",
        lambda: changeset.validate(current_version=current_version),
    )

    denied = OkfChangeSet(
        id="denied-proposal",
        base_version="catalog-42",
        proposer=changeset.proposer,
        justification="Tentar tocar policy.",
        operations=(
            ChangeOperation(
                "create-policy",
                "create",
                _document(
                    "policy",
                    "ticket-policy",
                    {"enforcement": "external", "sources": ["entra"]},
                ),
                "Não permitido.",
                evidence=(ChangeEvidence("spec", "user:request"),),
            ),
        ),
    )
    check(
        "operation outside writes is denied",
        lambda: denied.validate(current_version=current_version),
        fails=True,
    )

    cyclic = _valid_changeset()
    cyclic = OkfChangeSet(
        id=cyclic.id,
        base_version=cyclic.base_version,
        proposer=cyclic.proposer,
        justification=cyclic.justification,
        operations=(
            ChangeOperation(
                "first",
                "create",
                cyclic.operations[0].document,
                "Primeiro.",
                depends_on=("second",),
                evidence=(ChangeEvidence("spec", "catalog:first"),),
            ),
            ChangeOperation(
                "second",
                "create",
                cyclic.operations[1].document,
                "Segundo.",
                depends_on=("first",),
                evidence=(ChangeEvidence("spec", "catalog:second"),),
            ),
        ),
    )
    check(
        "dependency cycle is denied",
        lambda: cyclic.validate(current_version=current_version),
        fails=True,
    )

    structured = changeset.to_dict(current_version=current_version)
    check("patch transport is structured", isinstance(structured["operations"], list))
    check(
        "patch identifies changed field paths",
        any(item["path"].endswith("spec.agent.name") for item in structured["operations"][0]["patch"]),
    )
    check("ChangeSet declares its base version", structured["base_version"] == "catalog-42")
    check("gaps are separate from references", structured["gaps"][0]["capability"] == "duplicate-ticket-check")
    check(
        "review markdown is generated only at the edge",
        changeset.render_review(current_version=current_version).startswith("# ChangeSet"),
    )
    check("proposal cannot be confirmed before review", not hasattr(changeset, "confirm"))

    factual_catalog = {
        "items": [
            {
                "kind": "agent",
                "id": "ticket-agent",
                "name": "ticket-agent",
                "version": "3",
                "source": "Microsoft Foundry Agents",
                "state": "active",
                "selectable": True,
            }
        ],
        "snapshot": {"id": "cat_0123456789abcdef01234567", "hash": "a" * 64, "at": "2026-09-01T12:00:00Z"},
        "partial": False,
        "gaps": [],
    }
    builder_result = build_changeset_proposal(
        {
            "name": "new-ticket-agent",
            "description": "Atende solicitações de ticket.",
            "rationale": "Reutiliza a implementação já publicada.",
            "reuse": [{"name": "ticket-agent", "why": "Já atende tickets."}],
            "knowledge": ["support-kb"],
        },
        factual_catalog,
        tenant_id="tenant-a",
        area_id="support",
        actor_id="author-a",
    )
    builder_operations = builder_result["proposal"]["operations"]
    check("builder creates a multi-document proposal", len(builder_operations) == 2)
    check(
        "builder binds only the versioned catalog agent",
        lambda: parse_authoring_document(builder_operations[0]["document"]).spec["agent"]
        == {"name": "ticket-agent", "version": "3"},
    )
    check(
        "builder declares intra-set dependency",
        builder_operations[1]["depends_on"] == [builder_operations[0]["id"]],
    )
    check(
        "builder exposes evidence, justification and gaps per operation",
        all(operation["evidence"] and operation["justification"] and "gaps" in operation for operation in builder_operations),
    )
    check(
        "builder provenance identifies the process",
        lambda: parse_authoring_document(builder_operations[0]["document"]).generated["by"]
        == "process:builder",
    )
    check(
        "builder review requires an explicit decision per operation",
        lambda: review_changeset_proposal(
            builder_result["proposal"],
            [{"operation_id": builder_operations[0]["id"], "decision": "accept"}],
            factual_catalog,
            tenant_id="tenant-a",
            area_id="support",
        ),
        fails=True,
    )
    check(
        "builder review rejects duplicate decisions",
        lambda: review_changeset_proposal(
            builder_result["proposal"],
            [
                {"operation_id": builder_operations[0]["id"], "decision": "accept"},
                {"operation_id": builder_operations[0]["id"], "decision": "discard"},
            ],
            factual_catalog,
            tenant_id="tenant-a",
            area_id="support",
        ),
        fails=True,
    )
    reviewed_builder = review_changeset_proposal(
        builder_result["proposal"],
        [
            {"operation_id": operation["id"], "decision": "accept"}
            for operation in builder_operations
        ],
        factual_catalog,
        tenant_id="tenant-a",
        area_id="support",
    )
    check(
        "builder confirmation revalidates the complete graph",
        len(reviewed_builder["operations"]) == 2
        and len(reviewed_builder["confirmation_digest"]) == 64,
    )
    invented_binding = builder_operations[0]["document"].replace(
        "name: ticket-agent", "name: invented-agent"
    )
    check(
        "edited external reference must exist in the factual snapshot",
        lambda: review_changeset_proposal(
            builder_result["proposal"],
            [
                {
                    "operation_id": builder_operations[0]["id"],
                    "decision": "edit",
                    "edited_document": invented_binding,
                },
                {"operation_id": builder_operations[1]["id"], "decision": "accept"},
            ],
            factual_catalog,
            tenant_id="tenant-a",
            area_id="support",
        ),
        fails=True,
    )
    missing_result = build_changeset_proposal(
        {"name": "invented-agent", "reuse": []},
        {**factual_catalog, "items": []},
        tenant_id="tenant-a",
        area_id="support",
        actor_id="author-a",
    )
    check("missing implementation is a gap, not an invented binding", missing_result["proposal"] is None and missing_result["gaps"][0]["status"] == "missing")

    decisions = tuple(
        ChangeDecision(operation.id, "accept") for operation in changeset.operations
    )
    reviewed = changeset.review(decisions, current_version=current_version)
    check(
        "each document can be accepted",
        reviewed is not None and len(reviewed.changeset.operations) == 3,
    )
    confirmed = reviewed.confirm(current_version=current_version) if reviewed is not None else None
    check(
        "confirmation digest is stable only after review",
        confirmed is not None
        and confirmed.digest == reviewed.confirm(current_version=current_version).digest,
    )
    check(
        "reviewed state cannot be constructed directly",
        lambda: type(reviewed)(reviewed.changeset, None),
        fails=True,
    )
    check(
        "confirmed state cannot be constructed directly",
        lambda: type(confirmed)(reviewed, confirmed.digest, None),
        fails=True,
    )
    discarded = changeset.review(
        (ChangeDecision(operation.id, "discard") for operation in changeset.operations),
        current_version=current_version,
    )
    check("discarding the proposal leaves no ChangeSet", discarded is None)

    edited_agent = _document(
        "agent-binding",
        "ticket-agent",
        {"agent": {"name": "ticket-agent", "version": "2"}},
    )
    edited = changeset.review(
        (
            ChangeDecision(
                "create-agent",
                "edit",
                edited_agent,
                (ChangeEvidence("spec.agent", "human:review"),),
            ),
            ChangeDecision("create-mcp", "accept"),
            ChangeDecision("create-usecase", "accept"),
        ),
        current_version=current_version,
    )
    check(
        "editing replaces the document and its evidence",
        edited is not None
        and edited.changeset.operations[0].document.spec["agent"]["version"] == "2"
        and edited.changeset.operations[0].evidence[0].source == "human:review",
    )
    check(
        "editing invalidates the previous confirmation",
        edited is not None
        and confirmed is not None
        and edited.confirm(current_version=current_version).digest != confirmed.digest,
    )

    active = _document(
        "agent-binding",
        "existing-agent",
        {"agent": {"name": "existing-agent", "version": "1"}},
        publication_state="active",
    )
    revised = _document(
        "agent-binding",
        "existing-agent",
        {"agent": {"name": "existing-agent", "version": "2"}},
        revision="2",
        supersedes={"type": "agent-binding", "id": "existing-agent", "revision": "1"},
    )
    revision_change = OkfChangeSet(
        id="revision-proposal",
        base_version="catalog-42",
        proposer=changeset.proposer,
        justification="Revisar agente existente.",
        operations=(
            ChangeOperation(
                "revise-agent",
                "revise",
                revised,
                "Atualiza a versão do binding.",
                base_revision="1",
                evidence=(ChangeEvidence("spec.agent", "foundry:agent/existing-agent@2"),),
            ),
        ),
    )
    check(
        "revision with current base is accepted",
        lambda: revision_change.validate((active,), current_version=current_version),
    )
    stale = OkfChangeSet(
        id="stale-proposal",
        base_version="catalog-41",
        proposer=changeset.proposer,
        justification=revision_change.justification,
        operations=(
            ChangeOperation(
                "revise-agent",
                "revise",
                revised,
                "Usa base antiga.",
                base_revision="1",
                evidence=(ChangeEvidence("spec.agent", "foundry:agent/existing-agent@2"),),
            ),
        ),
    )
    check(
        "stale ChangeSet base version is denied",
        lambda: stale.validate((active,), current_version=current_version),
        fails=True,
    )
    revision_diff = revision_change.diffs((active,), current_version=current_version)[0]
    check("revision diff carries structured before and after", revision_diff.before is not None)
    check("semantic diff lists changed fields", any(change.kind == "replace" for change in revision_diff.changes))
    try:
        revision_diff.after["type"] = "policy"
    except TypeError:
        immutable_diff = True
    else:
        immutable_diff = False
    check("public diff snapshots are immutable", immutable_diff)

    deprecated = _document(
        "agent-binding",
        "existing-agent",
        {"agent": {"name": "existing-agent", "version": "1"}},
        revision="2",
        publication_state="deprecated",
        supersedes={"type": "agent-binding", "id": "existing-agent", "revision": "1"},
    )
    deprecation = OkfChangeSet(
        id="deprecation-proposal",
        base_version="catalog-42",
        proposer=changeset.proposer,
        justification="Deprecar binding existente.",
        operations=(
            ChangeOperation(
                "deprecate-agent",
                "deprecate",
                deprecated,
                "Retira o binding sem apagar histórico.",
                base_revision="1",
                evidence=(ChangeEvidence("publication_state", "human:review"),),
            ),
        ),
    )
    check(
        "deprecate creates a new immutable revision",
        lambda: deprecation.validate((active,), current_version=current_version),
    )
    check(
        "delete is outside the operation vocabulary",
        lambda: ChangeOperation(
            "delete-agent",
            "delete",
            deprecated,
            "Não permitido.",
            evidence=(ChangeEvidence("publication_state", "human:review"),),
        ),
        fails=True,
    )

    invented = _document(
        "usecase",
        "invented-reference",
        {
            "requires": [{"type": "mcp-binding", "id": "does-not-exist", "revision": "1"}],
            "targets": [{"type": "agent-binding", "id": "ticket-agent", "revision": "1"}],
            "approval": {"required": True, "role": "Approver"},
            "cost": {"kind": "unknown"},
            "citation": "required",
            "gaps": [],
        },
    )
    invented_change = OkfChangeSet(
        id="invented-reference-proposal",
        base_version="catalog-42",
        proposer=changeset.proposer,
        justification="Não aceitar capacidade inventada.",
        operations=(
            changeset.operations[0],
            ChangeOperation(
                "create-invented-usecase",
                "create",
                invented,
                "Referência inexistente.",
                depends_on=("create-agent",),
                evidence=(
                    ChangeEvidence("spec.requires", "user:request"),
                    ChangeEvidence("spec.targets", "catalog:ticket-capabilities"),
                    ChangeEvidence("spec.approval", "policy:tool-approval"),
                    ChangeEvidence("spec.cost", "catalog:ticket-capabilities"),
                    ChangeEvidence("spec.citation", "policy:assurance"),
                    ChangeEvidence("spec.gaps", "builder:analysis"),
                ),
            ),
        ),
    )
    check(
        "invented external reference is denied",
        lambda: invented_change.validate(current_version=current_version),
        fails=True,
    )

    missing_dependency = OkfChangeSet(
        id="missing-dependency-proposal",
        base_version=changeset.base_version,
        proposer=changeset.proposer,
        justification=changeset.justification,
        operations=(
            changeset.operations[0],
            changeset.operations[1],
            ChangeOperation(
                "create-usecase",
                "create",
                changeset.operations[2].document,
                "Omite a ordem exigida pelas referências.",
                evidence=changeset.operations[2].evidence,
            ),
        ),
    )
    check(
        "internal reference requires producer dependency",
        lambda: missing_dependency.validate(current_version=current_version),
        fails=True,
    )

    invalid_evidence = OkfChangeSet(
        id="invalid-evidence-proposal",
        base_version=changeset.base_version,
        proposer=changeset.proposer,
        justification="Não aceitar procedência sem campo real.",
        operations=(
            ChangeOperation(
                "create-agent",
                "create",
                changeset.operations[0].document,
                "Campo de evidência inventado.",
                evidence=(ChangeEvidence("spec.missing", "model:guess"),),
            ),
        ),
    )
    check(
        "evidence must point to a real changed field",
        lambda: invalid_evidence.validate(current_version=current_version),
        fails=True,
    )

    check(
        "connection is denied before entering a ChangeSet",
        lambda: _document("connection", "ticket-connection", {}),
        fails=True,
    )

    gap_only = OkfChangeSet(
        id="invented-name-as-gap",
        base_version=changeset.base_version,
        proposer=changeset.proposer,
        justification="Registrar ausência sem fabricar referência.",
        operations=(changeset.operations[0],),
        gaps=(ChangeGap("does-not-exist", "Nenhum recurso correspondente no catálogo."),),
    )
    check(
        "invented name is representable as a gap",
        lambda: gap_only.validate(current_version=current_version),
    )

    from app.modules.authoring.public import (
        BundleService,
        ChangeSetConflict,
        ChangeSetPreconditionFailed,
        ChangeSetScope,
        ChangeSetService,
        PostgresChangeSetRepository,
        SQLiteChangeSetRepository,
    )

    def repository_contract(label: str, repository_factory) -> None:
        scope = ChangeSetScope("tenant-a", "area-a", "author-a")
        other_tenant = ChangeSetScope("tenant-b", "area-a", "author-a")
        other_area = ChangeSetScope("tenant-a", "area-b", "author-a")
        service = ChangeSetService(repository_factory())
        content = {
            "justification": "Criar composição",
            "operations": [{"id": "create-agent", "operation": "create"}],
            "credentials": {"access_token": "must-not-persist"},
        }
        route_document = _document(
            "agent-binding",
            "route-agent",
            {
                "agent": {"name": "route-agent", "version": "1"},
                "authoringRoute": "workflow",
            },
            area="area-a",
        )
        embedded_document = serialize_authoring_document(
            replace(route_document, resource="workflow:workflows/route-agent.yaml")
        )
        embedded, _ = service.create(
            scope,
            source="manual",
            base_snapshot_id="snapshot-42",
            content={"operations": [{
                "id": "create-route-agent",
                "operation": "create",
                "document_type": "agent-binding",
                "document": embedded_document,
            }]},
            idempotency_key="request-embedded-document",
        )
        check(f"{label}: valid embedded OKF document is persisted", embedded.revision == 1)
        for route in ("prompt", "workflow", "container"):
            route_reference = (
                f"registry.example/{route}-agent@sha256:{'a' * 64}"
                if route == "container"
                else f"definitions/{route}-agent.yaml"
            )
            routed_document = serialize_authoring_document(
                replace(
                    route_document,
                    id=f"{route}-agent",
                    resource=f"{route}:{route_reference}",
                    spec={"agent": {"name": f"{route}-agent", "version": "1"}, "authoringRoute": route},
                )
            )
            routed, _ = service.create(
                scope,
                source="manual",
                base_snapshot_id="snapshot-42",
                content={"operations": [{
                    "id": f"create-{route}-agent",
                    "operation": "create",
                    "document_type": "agent-binding",
                    "document": routed_document,
                }]},
                idempotency_key=f"request-{label}-{route}-route",
            )
            reopened_route = service.get(scope, routed.id)
            check(
                f"{label}: {route} route round-trips",
                reopened_route.content["operations"][0]["document"] == routed_document,
            )
        check(
            f"{label}: embedded document cannot cross area scope",
            lambda: service.create(
                other_area,
                source="manual",
                base_snapshot_id="snapshot-42",
                content={"operations": [{
                    "id": "create-route-agent",
                    "operation": "create",
                    "document_type": "agent-binding",
                    "document": embedded_document,
                }]},
                idempotency_key="request-cross-scope-document",
            ),
            fails=True,
        )
        check(
            f"{label}: malformed embedded document is rejected",
            lambda: service.create(
                scope,
                source="manual",
                base_snapshot_id="snapshot-42",
                content={"operations": [{
                    "id": "create-invalid-agent",
                    "operation": "create",
                    "document_type": "agent-binding",
                    "document": "not an OKF document",
                }]},
                idempotency_key="request-invalid-document",
            ),
            fails=True,
        )
        check(
            f"{label}: operation requires an id",
            lambda: service.create(
                scope,
                source="manual",
                base_snapshot_id="snapshot-42",
                content={"operations": [{"operation": "create"}]},
                idempotency_key="request-missing-id",
            ),
            fails=True,
        )
        check(
            f"{label}: operation uses the OKF verb vocabulary",
            lambda: service.create(
                scope,
                source="manual",
                base_snapshot_id="snapshot-42",
                content={"operations": [{"id": "create-agent", "operation": "publish"}]},
                idempotency_key="request-invalid-verb",
            ),
            fails=True,
        )
        created, replay = service.create(
            scope,
            source="manual",
            base_snapshot_id="snapshot-42",
            content=content,
            idempotency_key="request-create-001",
        )
        check(f"{label}: first create is not replay", replay is False)
        check(f"{label}: first revision is immutable revision 1", created.revision == 1)
        check(
            f"{label}: sensitive values are redacted before persistence",
            "must-not-persist" not in repr(created.to_dict()),
        )
        replayed, replay = service.create(
            scope,
            source="manual",
            base_snapshot_id="snapshot-42",
            content=content,
            idempotency_key="request-create-001",
        )
        check(f"{label}: idempotent replay returns the aggregate", replay and replayed.id == created.id)
        check(
            f"{label}: idempotency key cannot identify another request",
            lambda: service.create(
                scope,
                source="manual",
                base_snapshot_id="snapshot-42",
                content={"operations": [{"id": "different", "operation": "create"}]},
                idempotency_key="request-create-001",
            ),
            fails=True,
        )
        check(f"{label}: tenant isolation is fail-closed", lambda: service.get(other_tenant, created.id), fails=True)
        check(f"{label}: area isolation is fail-closed", lambda: service.get(other_area, created.id), fails=True)
        updated = service.update(
            scope,
            created.id,
            expected_etag=created.etag,
            content={"justification": "Revisado", "operations": content["operations"]},
        )
        check(f"{label}: edit appends revision 2", updated.revision == 2 and updated.etag != created.etag)
        check(
            f"{label}: revision 1 remains immutable",
            service.get_revision(scope, created.id, 1).content_hash
            == created.content_hash,
        )
        check(
            f"{label}: list returns only the current scope",
            created.id in {record.id for record in service.list(scope)}
            and created.id not in {record.id for record in service.list(other_area)},
        )
        submitted = service.submit(scope, created.id, expected_etag=updated.etag)
        check(f"{label}: submit freezes the current revision", submitted.state == "submitted")
        check(
            f"{label}: submitted version cannot be overwritten",
            lambda: service.update(
                scope,
                created.id,
                expected_etag=submitted.etag,
                content={"operations": content["operations"]},
            ),
            fails=True,
        )
        derived = service.revise(scope, created.id, expected_etag=submitted.etag)
        check(
            f"{label}: editing after submit creates a new draft revision",
            derived.state == "draft" and derived.revision == 3,
        )
        check(
            f"{label}: submitted revision remains frozen in history",
            service.get_revision(scope, created.id, 2).state == "submitted",
        )
        check(
            f"{label}: stale If-Match cannot overwrite",
            lambda: service.update(
                scope,
                created.id,
                expected_etag=created.etag,
                content={"operations": content["operations"]},
            ),
            fails=True,
        )
        reopened = ChangeSetService(repository_factory()).get(scope, created.id)
        check(f"{label}: current revision survives repository restart", reopened.revision == 3)
        check(
            f"{label}: stale write left the current revision unchanged",
            reopened.content["justification"] == "Revisado",
        )

    with tempfile.TemporaryDirectory() as directory:
        sqlite_path = Path(directory) / "changesets.sqlite3"
        repository_contract("sqlite", lambda: SQLiteChangeSetRepository(sqlite_path))
        postgres_path = Path(directory) / "postgres-contract.sqlite3"
        repository_contract(
            "postgres",
            lambda: PostgresChangeSetRepository(lambda: _PostgresConnection(postgres_path)),
        )

        bundle_scope = ChangeSetScope("tenant-a", "area-a", "bundle-author")
        bundle_changesets = ChangeSetService(
            SQLiteChangeSetRepository(Path(directory) / "bundles.sqlite3")
        )
        policy_document = _document(
            "policy",
            "safe-output",
            {"enforcement": "external", "sources": ["policy-engine"]},
            area="area-a",
        )
        bundle_document = _document(
            "bundle",
            "support-bundle",
            {
                "includes": [
                    {"type": "policy", "id": "safe-output", "revision": "1"}
                ]
            },
            area="area-a",
        )
        bundle_record, _ = bundle_changesets.create(
            bundle_scope,
            source="manual",
            base_snapshot_id="snapshot-42",
            content={
                "operations": [
                    {
                        "id": "create-policy",
                        "operation": "create",
                        "document_type": "policy",
                        "document": serialize_authoring_document(policy_document),
                    },
                    {
                        "id": "create-bundle",
                        "operation": "create",
                        "document_type": "bundle",
                        "document": serialize_authoring_document(bundle_document),
                    },
                ]
            },
            idempotency_key="bundle-create-001",
        )
        bundles = BundleService(bundle_changesets, ())
        projected = bundles.get(bundle_scope, bundle_record.id)
        check(
            "bundle resolves references from the same revision",
            projected["canSubmit"]
            and projected["dependencies"][0]["source"] == "changeset",
        )
        blocked_record, _ = bundle_changesets.create(
            bundle_scope,
            source="manual",
            base_snapshot_id="snapshot-42",
            content={
                "operations": bundle_record.to_dict()["content"]["operations"],
                "gaps": [{"id": "missing-approval", "reason": "Pendente"}],
            },
            idempotency_key="bundle-blocked-001",
        )
        check(
            "blocking gaps prevent bundle submission",
            lambda: bundles.submit(
                bundle_scope, blocked_record.id, expected_etag=blocked_record.etag
            ),
            fails=True,
        )
        submitted_bundle = bundles.submit(
            bundle_scope, bundle_record.id, expected_etag=bundle_record.etag
        )
        revised_bundle = bundles.revise(
            bundle_scope, bundle_record.id, expected_etag=submitted_bundle["etag"]
        )
        check(
            "bundle detail pins one immutable revision",
            revised_bundle["revision"] == 2
            and bundles.get(bundle_scope, bundle_record.id, revision=1)["state"]
            == "submitted",
        )

        raw = sqlite_path.read_bytes()
        check("database contains no delegated credential", b"must-not-persist" not in raw)

        from app.modules.authoring import api as authoring_api

        api_service = ChangeSetService(SQLiteChangeSetRepository(Path(directory) / "api.sqlite3"))
        api_scope = ChangeSetScope("tenant-a", "area-a", "author-a")
        application = FastAPI()
        application.include_router(authoring_api.router)
        application.dependency_overrides[authoring_api.require_area] = lambda: None
        application.dependency_overrides[authoring_api._scope] = lambda: api_scope
        application.dependency_overrides[authoring_api.default_changeset_service] = lambda: api_service
        from app.shared import auth

        api_user = SimpleNamespace(oid="author-a", roles=["Author"])
        application.dependency_overrides[auth.require_user] = lambda: api_user
        if auth.azure_scheme is not None:
            application.dependency_overrides[auth.azure_scheme] = lambda: api_user
        client = TestClient(application)
        bundle_write_routes = [
            route
            for route in application.routes
            if isinstance(route, APIRoute)
            and route.path.startswith("/authoring/bundles/")
            and route.methods != {"GET"}
        ]
        bundle_author_dependency = authoring_api._bundle_author[0].dependency
        application.dependency_overrides[bundle_author_dependency] = lambda: (
            _ for _ in ()
        ).throw(HTTPException(403, "AUTHOR_REQUIRED"))
        forbidden_bundle = client.post(
            f"/authoring/bundles/{'0' * 8}-{'0' * 4}-4000-8000-{'0' * 12}/submit",
            headers={"If-Match": f'"1:{"0" * 64}"'},
        )
        check(
            "bundle writes require Author and do not grant Admin implicitly",
            len(bundle_write_routes) == 3 and forbidden_bundle.status_code == 403,
        )
        application.dependency_overrides.pop(bundle_author_dependency)
        payload = {
            "source": "manual",
            "base_snapshot_id": "snapshot-42",
            "content": {
                "operations": [{"id": "create-agent", "operation": "create"}],
                "access_token": "api-secret",
            },
        }
        created_response = client.post(
            "/authoring/changesets",
            json=payload,
            headers={"Idempotency-Key": "api-create-001"},
        )
        changeset_id = created_response.json().get("id", "")
        etag = created_response.headers.get("etag", "")
        check("api: POST creates revision with ETag", created_response.status_code == 201 and bool(etag))
        check("api: response does not expose credential", "api-secret" not in created_response.text)
        replay_response = client.post(
            "/authoring/changesets",
            json=payload,
            headers={"Idempotency-Key": "api-create-001"},
        )
        check("api: POST replay returns 200", replay_response.status_code == 200)
        read_response = client.get(f"/authoring/changesets/{changeset_id}")
        check("api: GET returns current revision", read_response.status_code == 200 and read_response.json()["revision"] == 1)
        updated_response = client.patch(
            f"/authoring/changesets/{changeset_id}",
            json={"content": {"operations": payload["content"]["operations"], "justification": "updated"}},
            headers={"If-Match": etag},
        )
        check("api: PATCH appends revision", updated_response.status_code == 200 and updated_response.json()["revision"] == 2)
        stale_response = client.patch(
            f"/authoring/changesets/{changeset_id}",
            json={"content": {"operations": payload["content"]["operations"]}},
            headers={"If-Match": etag},
        )
        check("api: stale If-Match returns 412", stale_response.status_code == 412)
        application.dependency_overrides[authoring_api._scope] = lambda: ChangeSetScope("tenant-a", "area-b", "author-a")
        cross_area = client.get(f"/authoring/changesets/{changeset_id}")
        check("api: cross-area read is indistinguishable from absent", cross_area.status_code == 404)

        from app.modules.proposer import api as proposer_api

        builder_service = ChangeSetService(
            SQLiteChangeSetRepository(Path(directory) / "builder-api.sqlite3")
        )
        builder_application = FastAPI()
        builder_application.include_router(proposer_api.router)
        builder_application.dependency_overrides[proposer_api.require_area] = lambda: None
        builder_application.dependency_overrides[
            proposer_api.default_changeset_service
        ] = lambda: builder_service
        builder_application.dependency_overrides[auth.require_user] = lambda: api_user
        if auth.azure_scheme is not None:
            builder_application.dependency_overrides[auth.azure_scheme] = lambda: api_user
        proposer_api.current_area = lambda: SimpleNamespace(id="support")
        proposer_api.current_tenant_id = lambda: "tenant-a"
        proposer_api.current_user = lambda: api_user
        proposer_api._complete_catalog = lambda: factual_catalog
        builder_client = TestClient(builder_application)
        confirmation_payload = {
            "proposal": builder_result["proposal"],
            "decisions": [
                {"operation_id": operation["id"], "decision": "accept"}
                for operation in builder_operations
            ],
        }
        confirmed_response = builder_client.post(
            "/proposer/changeset/confirm",
            json=confirmation_payload,
            headers={
                "X-Area-ID": "support",
                "Idempotency-Key": "builder-confirm-001",
            },
        )
        confirmed_body = confirmed_response.json()
        check(
            "builder api: confirmation persists one inert draft",
            confirmed_response.status_code == 200
            and confirmed_body["state"] == "draft"
            and confirmed_body["source"] == "builder",
        )
        replayed_confirmation = builder_client.post(
            "/proposer/changeset/confirm",
            json=confirmation_payload,
            headers={
                "X-Area-ID": "support",
                "Idempotency-Key": "builder-confirm-001",
            },
        )
        check(
            "builder api: confirmation is idempotent",
            replayed_confirmation.status_code == 200
            and replayed_confirmation.json()["id"] == confirmed_body["id"]
            and replayed_confirmation.json()["revision"] == 1,
        )

    check("domain exposes conflict type", issubclass(ChangeSetConflict, AuthoringInvalid))
    check("domain exposes precondition type", issubclass(ChangeSetPreconditionFailed, AuthoringInvalid))

    print(f"\n{'❌' if failures else '✅'} {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
