"""Contrato de reconciliação pós-merge da saga de publicação."""

from __future__ import annotations

import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import app.modules.foundry.public as foundry_public
from app.modules.publication.internal.reconciliation import (
    JournalEntry,
    MaterializationStep,
    MergeEvidence,
    OfficialFoundryMaterializer,
    ReconciliationBlocked,
    ReconciliationService,
    SQLiteMaterializationJournal,
)


@dataclass
class _Publication:
    id: str = "publication-1"
    state: str = "pr_open"
    content_hash: str = "a" * 64
    changeset_id: str = "changeset-1"
    revision: int = 1


@dataclass
class _Scope:
    tenant_id: str = "tenant-1"
    area_id: str = "area-1"


class _Publications:
    def __init__(self, publication: _Publication) -> None:
        self.publication = publication
        self.states: list[str] = []

    def transition_reconciliation(self, scope, publication_id, **values):
        assert self.publication.state in values["expected_states"]
        self.publication.state = values["state"]
        self.states.append(values["state"])
        return self.publication


class _Materializer:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def materialize(self, step, *, provenance) -> dict[str, str]:
        self.calls.append(step.operation_id)
        return {"name": step.name}

    def compensate(self, entry) -> bool:
        return True


class _SagaMaterializer:
    def __init__(self, *, fail_on: str = "", compensate: bool = True) -> None:
        self.fail_on = fail_on
        self.can_compensate = compensate
        self.created: list[str] = []
        self.compensated: list[str] = []

    def materialize(self, step, *, provenance) -> dict[str, str]:
        if step.operation_id == self.fail_on:
            raise RuntimeError("official surface failed")
        self.created.append(step.operation_id)
        return {"name": step.name, "version": f"v-{step.position}"}

    def compensate(self, entry: JournalEntry) -> bool:
        self.compensated.append(entry.operation_id)
        return self.can_compensate


def _assert_blocked(evidence: MergeEvidence, expected_code: str) -> None:
    materializer = _Materializer()
    service = ReconciliationService(materializer)
    blocked_code = ""
    try:
        service.reconcile(_Publication(), evidence)
    except ReconciliationBlocked as exc:
        blocked_code = str(exc)
    else:
        raise AssertionError(f"expected {expected_code}")
    assert blocked_code == expected_code
    assert materializer.calls == []


def main() -> None:
    _assert_blocked(
        MergeEvidence(merged=False, commit_id="", content_hash=""),
        "PUBLICATION_NOT_MERGED",
    )
    _assert_blocked(
        MergeEvidence(merged=True, commit_id="commit-1", content_hash="b" * 64),
        "PUBLICATION_CONTENT_HASH_MISMATCH",
    )

    materializer = _Materializer()
    service = ReconciliationService(materializer)
    result = service.reconcile(
        _Publication(),
        MergeEvidence(merged=True, commit_id="commit-1", content_hash="a" * 64),
    )
    assert result.commit_id == "commit-1"
    assert materializer.calls == ["publication-1"]

    operations = [
        {"id": "binding", "operation": "create"},
        {
            "id": "agent-one",
            "operation": "create",
            "materialization": {"kind": "agent", "name": "agent-one", "payload": {}},
        },
        {
            "id": "skill-one",
            "operation": "create",
            "materialization": {"kind": "skill", "name": "skill-one", "payload": {}},
        },
    ]
    evidence = MergeEvidence(True, "commit-2", "a" * 64)
    with tempfile.TemporaryDirectory() as directory:
        scope = _Scope()
        publication = _Publication()
        publications = _Publications(publication)
        journal = SQLiteMaterializationJournal(Path(directory) / "journal.sqlite3")
        saga_materializer = _SagaMaterializer()
        saga = ReconciliationService(
            saga_materializer, journal=journal, publications=publications
        )
        completed = saga.reconcile(
            publication, evidence, scope=scope, operations=operations
        )
        assert completed.state == "completed"
        assert [entry.status for entry in completed.journal] == [
            "skipped",
            "completed",
            "completed",
        ]
        assert saga_materializer.created == ["agent-one", "skill-one"]

        publication.state = "materializing"
        saga.reconcile(publication, evidence, scope=scope, operations=operations)
        assert saga_materializer.created == ["agent-one", "skill-one"]

    with tempfile.TemporaryDirectory() as directory:
        scope = _Scope()
        publication = _Publication(id="publication-2")
        publications = _Publications(publication)
        journal = SQLiteMaterializationJournal(Path(directory) / "journal.sqlite3")
        saga_materializer = _SagaMaterializer(fail_on="skill-one", compensate=False)
        saga = ReconciliationService(
            saga_materializer, journal=journal, publications=publications
        )
        try:
            saga.reconcile(publication, evidence, scope=scope, operations=operations)
        except RuntimeError:
            pass
        else:
            raise AssertionError("expected materialization failure")
        assert publication.state == "compensation_required"
        assert saga_materializer.compensated == ["agent-one"]
        entries = journal.list(scope, publication.id)
        assert entries[2].status == "compensation_required"
        assert entries[2].error_code == "PUBLICATION_MATERIALIZATION_OUTCOME_UNKNOWN"
        saga_materializer.can_compensate = True
        saga.compensate(scope, publication)
        assert publication.state == "compensation_required"
        assert saga_materializer.created == ["agent-one"]

    with tempfile.TemporaryDirectory() as directory:
        scope = _Scope()
        publication = _Publication(id="publication-3", state="materializing")
        publications = _Publications(publication)
        journal = SQLiteMaterializationJournal(Path(directory) / "journal.sqlite3")
        journal.ensure(
            scope,
            publication.id,
            (MaterializationStep(0, "agent-one", "agent", "agent-one", {}),),
        )
        journal.mark(scope, publication.id, 0, status="executing")
        saga_materializer = _SagaMaterializer()
        saga = ReconciliationService(
            saga_materializer, journal=journal, publications=publications
        )
        busy_code = ""
        try:
            saga.reconcile(
                publication,
                evidence,
                scope=scope,
                operations=[operations[1]],
            )
        except ReconciliationBlocked as exc:
            busy_code = str(exc)
        assert busy_code == "PUBLICATION_MATERIALIZATION_BUSY"
        assert publication.state == "materializing"
        assert saga_materializer.created == []

        connection = journal._connect()
        try:
            connection.execute(
                """UPDATE publication_materialization_journal SET updated_at = ?
                   WHERE tenant_id = ? AND area_id = ? AND publication_id = ?""",
                (
                    (datetime.now(UTC) - timedelta(minutes=6)).isoformat(),
                    scope.tenant_id,
                    scope.area_id,
                    publication.id,
                ),
            )
            connection.commit()
        finally:
            connection.close()
        resumed = saga.reconcile(
            publication,
            evidence,
            scope=scope,
            operations=[operations[1]],
        )
        assert resumed.state == "compensation_required"
        assert saga_materializer.created == []

    with tempfile.TemporaryDirectory() as directory:
        scope = _Scope()
        publication = _Publication(id="publication-4")
        publications = _Publications(publication)
        journal = SQLiteMaterializationJournal(Path(directory) / "journal.sqlite3")
        saga_materializer = _SagaMaterializer()
        saga = ReconciliationService(
            saga_materializer, journal=journal, publications=publications
        )
        knowledge_operations = [
            {
                "id": "knowledge-one",
                "materialization": {
                    "kind": "knowledge",
                    "name": "knowledge-one",
                    "payload": {},
                },
            }
        ]
        try:
            saga.reconcile(
                publication,
                evidence,
                scope=scope,
                operations=knowledge_operations,
            )
        except ReconciliationBlocked as exc:
            blocked_code = str(exc)
        else:
            raise AssertionError("expected knowledge materialization to be blocked")
        assert blocked_code == "PUBLICATION_MATERIALIZATION_UNSUPPORTED"
        assert saga_materializer.created == []
        assert journal.list(scope, publication.id) == ()

        steps = (MaterializationStep(0, "agent-one", "agent", "agent-one", {}),)
        journal.ensure(scope, publication.id, steps)
        assert journal.claim(scope, publication.id, 0) is True
        assert journal.claim(scope, publication.id, 0) is False

    with tempfile.TemporaryDirectory() as directory:
        scope = _Scope()
        journal = SQLiteMaterializationJournal(Path(directory) / "journal.sqlite3")
        steps = (MaterializationStep(0, "agent-one", "agent", "agent-one", {}),)
        journal.ensure(scope, "publication-5", steps)
        with ThreadPoolExecutor(max_workers=2) as executor:
            claims = list(
                executor.map(
                    lambda _: journal.claim(scope, "publication-5", 0),
                    range(2),
                )
            )
        assert sorted(claims) == [False, True]

    original = foundry_public.create_toolbox_version
    calls: list[dict] = []
    try:
        foundry_public.create_toolbox_version = lambda name, payload, **kwargs: (
            calls.append(kwargs) or {"name": name, "version": "1"}
        )
        OfficialFoundryMaterializer().materialize(
            MaterializationStep(
                0,
                "toolbox-one",
                "toolbox",
                "toolbox-one",
                {"tools": [{"type": "mcp"}]},
            ),
            provenance={"publication_id": "publication-6"},
        )
    finally:
        foundry_public.create_toolbox_version = original
    assert calls == [{"ensure_connection": False}]

    print("publication reconciliation: passed")


if __name__ == "__main__":
    main()
