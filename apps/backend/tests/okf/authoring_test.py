"""Permissões declarativas dentro do perfil de autoria do copiloto."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.modules.okf.public import (
    AuthoringInvalid,
    copilot_allows,
    parse_authoring_document,
)
from tests.okf.envelope_test import DOCUMENT as AGENT_BINDING_DOCUMENT

DOCUMENT = """---
type: copilot
status: draft
generated:
  by: process:builder
  at: "2026-08-31T12:00:00Z"
x-foundry-authoring:
  profile_version: "1"
  id: ticket-builder
  revision: "1"
  publication_state: proposed
  tenant: tenant-a
  area: support
  spec:
    writes:
      - type: usecase
        operations: [create, revise]
      - type: policy
        operations: [revise]
    cannotWrite:
      - type: usecase
      - type: policy
      - type: connection
      - type: middleware-implementation
      - type: tenant-config
---

# Ticket builder
"""


def main() -> int:
    failures: list[str] = []

    def check(name: str, condition: bool) -> None:
        print(f"  {'✓' if condition else '✗'} {name}")
        if not condition:
            failures.append(name)

    document = parse_authoring_document(DOCUMENT)
    check("cannotWrite overrides writes", not copilot_allows(document, "usecase", "create"))
    check("policy is never authorable", not copilot_allows(document, "policy", "revise"))
    check("missing grant is denied", not copilot_allows(document, "agent-binding", "create"))
    check("unknown operation is denied", not copilot_allows(document, "usecase", "publish"))

    allowed = parse_authoring_document(DOCUMENT.replace("      - type: usecase\n      - type: policy", "      - type: policy"))
    check("declared operation is allowed", copilot_allows(allowed, "usecase", "create"))
    check("undeclared operation is denied", not copilot_allows(allowed, "usecase", "deprecate"))

    def refuses(name: str, old: str, new: str) -> None:
        try:
            parse_authoring_document(DOCUMENT.replace(old, new), where=name)
        except AuthoringInvalid:
            check(name, True)
        else:
            check(name, False)

    refuses("unknown operation fails schema", "operations: [create, revise]", "operations: [create, publish]")
    refuses("cannotWrite cannot carry operations", "      - type: connection", "      - {type: connection, operations: [create]}")
    refuses(
        "duplicate write rule is ambiguous",
        "      - type: policy\n        operations: [revise]",
        "      - type: usecase\n        operations: [revise]",
    )

    from app.modules.authoring.public import (
        ChangeSetScope,
        ChangeSetService,
        SQLiteChangeSetRepository,
        SQLiteValidationReportRepository,
        ValidationService,
        ValidationTransitionBlocked,
    )

    with tempfile.TemporaryDirectory() as directory:
        scope = ChangeSetScope("tenant-a", "support", "author-a")
        changesets = ChangeSetService(
            SQLiteChangeSetRepository(Path(directory) / "authoring.sqlite3")
        )
        record, _ = changesets.create(
            scope,
            source="manual",
            base_snapshot_id="snapshot-1",
            content={
                "operations": [
                    {
                        "id": "create-copilot",
                        "operation": "create",
                        "document_type": "copilot",
                        "document": DOCUMENT,
                    }
                ]
            },
            idempotency_key="validation-report-001",
        )
        validations = ValidationService(
            changesets,
            SQLiteValidationReportRepository(Path(directory) / "authoring.sqlite3"),
            sources=(),
        )
        first = validations.run(scope, record.id, revision=1, phase="submission")
        second = validations.run(scope, record.id, revision=1, phase="submission")
        check(
            "validation executions append immutable reports",
            first.id != second.id
            and validations.get(scope, first.id).content_hash == record.content_hash,
        )
        azure = next(check for check in first.checks if check.id == "azure-readiness")
        check(
            "external readiness stays pending without Azure",
            azure.status == "pending" and azure.source == "azure" and not azure.blocking,
        )
        check(
            "deterministic checks carry real execution evidence",
            all(
                check.evidence
                for check in first.checks
                if check.source == "local"
            ),
        )
        validations.assert_transition(scope, record.id, phase="submission")
        blocked_record, _ = changesets.create(
            scope,
            source="manual",
            base_snapshot_id="snapshot-1",
            content={
                "operations": record.to_dict()["content"]["operations"],
                "gaps": [{"id": "missing-policy", "reason": "Policy ausente"}],
            },
            idempotency_key="validation-report-blocked",
        )
        blocked = validations.run(
            scope, blocked_record.id, revision=1, phase="approval"
        )
        try:
            validations.assert_transition(
                scope, blocked_record.id, phase="approval"
            )
        except ValidationTransitionBlocked:
            check(
                "failed blocking check prevents the phase transition",
                blocked.blocks_transition,
            )
        else:
            check("failed blocking check prevents the phase transition", False)

        from app.modules.authoring import api as authoring_api
        from app.shared import auth

        application = FastAPI()
        application.include_router(authoring_api.router)
        application.dependency_overrides[authoring_api.require_area] = lambda: None
        application.dependency_overrides[authoring_api._scope] = lambda: scope
        application.dependency_overrides[
            authoring_api.default_validation_service
        ] = lambda: validations
        api_user = SimpleNamespace(oid="author-a", roles=["Author"])
        application.dependency_overrides[auth.require_user] = lambda: api_user
        if auth.azure_scheme is not None:
            application.dependency_overrides[auth.azure_scheme] = lambda: api_user
        client = TestClient(application)
        check(
            "validation role matrix has no implicit inheritance",
            authoring_api._validation_role_allowed("submission", {"Author"})
            and not authoring_api._validation_role_allowed("submission", {"Approver"})
            and authoring_api._validation_role_allowed("approval", {"Approver"})
            and not authoring_api._validation_role_allowed("approval", {"Author", "Admin"}),
        )
        response = client.post(
            f"/authoring/changesets/{record.id}/validations",
            json={"revision": 1, "phase": "submission"},
        )
        report_id = response.json().get("id", "")
        listed = client.get(
            f"/authoring/changesets/{record.id}/validations?revision=1&phase=submission"
        )
        check(
            "api creates and lists a report for the exact revision and phase",
            response.status_code == 201
            and response.json().get("revision") == 1
            and response.json().get("phase") == "submission"
            and any(item["id"] == report_id for item in listed.json().get("items", [])),
        )
        application.dependency_overrides[authoring_api._scope] = lambda: ChangeSetScope(
            "tenant-a", "another-area", "author-a"
        )
        cross_area = client.get(
            f"/authoring/changesets/{record.id}/validations"
        )
        check(
            "api validation history is fail-closed across areas",
            cross_area.status_code == 404,
        )

        external_document = AGENT_BINDING_DOCUMENT.replace(
            "  supersedes:\n    type: agent-binding\n    id: ticket-builder\n    revision: \"1\"\n",
            "",
        ).replace(
            "  spec:\n    agent:",
            "  spec:\n    requires:\n      - type: agent-binding\n        id: shared-agent\n      - type: agent-binding\n        id: versioned-agent\n        revision: \"3\"\n    agent:",
        )
        external_record, _ = changesets.create(
            scope,
            source="manual",
            base_snapshot_id="snapshot-1",
            content={
                "operations": [
                    {
                        "id": "create-agent-binding",
                        "operation": "create",
                        "document_type": "agent-binding",
                        "document": external_document,
                    }
                ]
            },
            idempotency_key="validation-external-references",
        )
        source = SimpleNamespace(
            kind="agent-binding",
            owner="Microsoft Foundry Agents",
            list_items=lambda: (),
            get_item=lambda _resource_id: {
                "id": _resource_id,
                "versions": [{"version": "3"}, {"version": "2"}],
            },
        )
        external_validations = ValidationService(
            changesets,
            SQLiteValidationReportRepository(Path(directory) / "authoring.sqlite3"),
            sources=(source,),
        )
        external_report = external_validations.run(
            scope, external_record.id, revision=1, phase="approval"
        )
        references = next(
            item for item in external_report.checks if item.id == "references"
        )
        check(
            "approval resolves floating and fixed external references factually",
            references.status == "approved"
            and references.evidence["resolvedExternal"] == 2,
        )
        unavailable_source = SimpleNamespace(
            kind="agent-binding",
            owner="Microsoft Foundry Agents",
            list_items=lambda: (),
            get_item=lambda _resource_id: (_ for _ in ()).throw(
                RuntimeError("upstream unavailable")
            ),
        )
        unavailable_validations = ValidationService(
            changesets,
            SQLiteValidationReportRepository(Path(directory) / "authoring.sqlite3"),
            sources=(unavailable_source,),
        )
        unavailable_report = unavailable_validations.run(
            scope, external_record.id, revision=1, phase="approval"
        )
        unavailable_references = next(
            item for item in unavailable_report.checks if item.id == "references"
        )
        check(
            "unavailable factual source stays pending and blocks dependent phase",
            unavailable_references.status == "pending"
            and unavailable_references.blocking
            and unavailable_references.evidence["unverifiable"] == 2,
        )

    print(f"\n{'❌' if failures else '✅'} {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
