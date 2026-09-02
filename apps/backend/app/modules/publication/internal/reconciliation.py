"""Reconciliação fail-closed, journal idempotente e compensação pós-merge."""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_MATERIALIZABLE = frozenset({"agent", "skill", "toolbox"})
_EXECUTION_LEASE_SECONDS = 300


class ReconciliationBlocked(RuntimeError):
    """A evidência ou a projeção ainda não autoriza materialização."""


@dataclass(frozen=True, slots=True)
class MergeEvidence:
    merged: bool
    commit_id: str
    content_hash: str


@dataclass(frozen=True, slots=True)
class MaterializationStep:
    position: int
    operation_id: str
    kind: str
    name: str
    payload: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class JournalEntry:
    position: int
    operation_id: str
    kind: str
    name: str
    status: str
    external_id: str = ""
    version: str = ""
    error_code: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    state: str
    commit_id: str
    journal: tuple[JournalEntry, ...]


class Materializer(Protocol):
    def materialize(self, step: MaterializationStep, *, provenance: Mapping[str, str]) -> Mapping[str, Any]: ...
    def compensate(self, entry: JournalEntry) -> bool: ...


class OfficialFoundryMaterializer:
    """Despacha apenas para as quatro superfícies oficiais verificadas na ADR-032."""

    def materialize(
        self, step: MaterializationStep, *, provenance: Mapping[str, str]
    ) -> Mapping[str, Any]:
        from app.modules.foundry.public import (
            create_agent_version,
            create_skill,
            create_toolbox_version,
        )

        payload = dict(step.payload)
        marker = " ".join(f"{key}={value}" for key, value in provenance.items())
        if step.kind == "agent":
            metadata = dict(payload.get("metadata") or {})
            metadata.update({f"publication.{key}": value for key, value in provenance.items()})
            payload["metadata"] = metadata
            return create_agent_version(step.name, payload, description=marker)
        if step.kind == "skill":
            metadata = dict(payload.get("metadata") or {})
            metadata.update({f"publication.{key}": value for key, value in provenance.items()})
            payload["metadata"] = metadata
            return create_skill(step.name, payload)
        if step.kind == "toolbox":
            description = str(payload.get("description") or "").strip()
            payload["description"] = f"{description}\n{marker}".strip()
            return create_toolbox_version(step.name, payload, ensure_connection=False)
        raise ReconciliationBlocked("PUBLICATION_MATERIALIZATION_UNSUPPORTED")

    def compensate(self, entry: JournalEntry) -> bool:
        if not entry.version:
            return False
        if entry.kind == "agent":
            from app.modules.foundry.public import delete_agent_version

            delete_agent_version(entry.name, entry.version)
            return True
        if entry.kind == "skill":
            from app.modules.foundry.public import delete_skill_version

            delete_skill_version(entry.name, entry.version)
            return True
        if entry.kind == "toolbox":
            from app.modules.foundry.public import delete_toolbox_version

            delete_toolbox_version(entry.name, entry.version)
            return True
        return False


class PublicationStateRepository(Protocol):
    def transition_reconciliation(
        self, scope: Any, publication_id: str, *, expected_states: Sequence[str],
        state: str, step: str, commit_id: str = "", merge_status: str = "",
        error_code: str = "", now: str,
    ) -> Any: ...


class SQLiteMaterializationJournal:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        connection = self._connect()
        try:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS publication_materialization_journal (
                    tenant_id TEXT NOT NULL, area_id TEXT NOT NULL,
                    publication_id TEXT NOT NULL, position BIGINT NOT NULL,
                    operation_id TEXT NOT NULL, kind TEXT NOT NULL, name TEXT NOT NULL,
                    status TEXT NOT NULL, external_id TEXT NOT NULL DEFAULT '',
                    version TEXT NOT NULL DEFAULT '', error_code TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, area_id, publication_id, position),
                    UNIQUE (tenant_id, area_id, publication_id, operation_id)
                )"""
            )
            connection.commit()
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path, timeout=5)

    @staticmethod
    def _scope(scope: Any) -> tuple[str, str]:
        return scope.tenant_id, scope.area_id

    def ensure(self, scope: Any, publication_id: str, steps: Sequence[MaterializationStep]) -> None:
        now = datetime.now(UTC).isoformat()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """SELECT position, operation_id, kind, name
                   FROM publication_materialization_journal
                   WHERE tenant_id = ? AND area_id = ? AND publication_id = ?
                   ORDER BY position""",
                (*self._scope(scope), publication_id),
            ).fetchall()
            expected = [(step.position, step.operation_id, step.kind, step.name) for step in steps]
            if existing and existing != expected:
                raise ReconciliationBlocked("PUBLICATION_JOURNAL_DIVERGED")
            if not existing:
                connection.executemany(
                    """INSERT INTO publication_materialization_journal
                       (tenant_id, area_id, publication_id, position, operation_id,
                        kind, name, status, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)""",
                    [(*self._scope(scope), publication_id, *item, now) for item in expected],
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def list(self, scope: Any, publication_id: str) -> tuple[JournalEntry, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                """SELECT position, operation_id, kind, name, status, external_id,
                          version, error_code, updated_at
                   FROM publication_materialization_journal
                   WHERE tenant_id = ? AND area_id = ? AND publication_id = ?
                   ORDER BY position""",
                (*self._scope(scope), publication_id),
            ).fetchall()
            return tuple(JournalEntry(*row) for row in rows)
        finally:
            connection.close()

    def mark(
        self, scope: Any, publication_id: str, position: int, *, status: str,
        external_id: str = "", version: str = "", error_code: str = "",
    ) -> None:
        connection = self._connect()
        try:
            changed = connection.execute(
                """UPDATE publication_materialization_journal
                   SET status = ?, external_id = ?, version = ?, error_code = ?, updated_at = ?
                   WHERE tenant_id = ? AND area_id = ? AND publication_id = ? AND position = ?""",
                (status, external_id, version, error_code, datetime.now(UTC).isoformat(),
                 *self._scope(scope), publication_id, position),
            ).rowcount
            if changed != 1:
                raise ReconciliationBlocked("PUBLICATION_JOURNAL_STEP_NOT_FOUND")
            connection.commit()
        finally:
            connection.close()

    def claim(self, scope: Any, publication_id: str, position: int) -> bool:
        connection = self._connect()
        try:
            changed = connection.execute(
                """UPDATE publication_materialization_journal
                   SET status = 'executing', updated_at = ?
                   WHERE tenant_id = ? AND area_id = ? AND publication_id = ?
                     AND position = ? AND status = 'pending'""",
                (
                    datetime.now(UTC).isoformat(),
                    *self._scope(scope),
                    publication_id,
                    position,
                ),
            ).rowcount
            connection.commit()
            return changed == 1
        finally:
            connection.close()


def _materialization_step(
    position: int, operation_id: str, projection: Any
) -> MaterializationStep:
    if projection is None:
        return MaterializationStep(position, operation_id, "git_only", operation_id, {})
    if not isinstance(projection, Mapping) or set(projection) != {"kind", "name", "payload"}:
        raise ReconciliationBlocked("PUBLICATION_MATERIALIZATION_INVALID")
    kind = str(projection.get("kind") or "")
    name = str(projection.get("name") or "")
    payload = projection.get("payload")
    if kind not in _MATERIALIZABLE:
        raise ReconciliationBlocked("PUBLICATION_MATERIALIZATION_UNSUPPORTED")
    if not _NAME.fullmatch(name) or not isinstance(payload, Mapping):
        raise ReconciliationBlocked("PUBLICATION_MATERIALIZATION_INVALID")
    return MaterializationStep(position, operation_id, kind, name, dict(payload))


def materialization_steps(
    operations: Sequence[Mapping[str, Any]],
) -> tuple[MaterializationStep, ...]:
    steps: list[MaterializationStep] = []
    for position, operation in enumerate(operations):
        operation_id = str(operation.get("id") or "")
        if not _NAME.fullmatch(operation_id):
            raise ReconciliationBlocked("PUBLICATION_OPERATION_ID_INVALID")
        steps.append(_materialization_step(position, operation_id, operation.get("materialization")))
    return tuple(steps)


class ReconciliationService:
    def __init__(
        self, materializer: Materializer, *, journal: SQLiteMaterializationJournal | None = None,
        publications: PublicationStateRepository | None = None,
    ) -> None:
        self._materializer = materializer
        self._journal = journal
        self._publications = publications

    def journal(self, scope: Any, publication_id: str) -> tuple[JournalEntry, ...]:
        if self._journal is None:
            return ()
        return self._journal.list(scope, publication_id)

    @staticmethod
    def _verify(publication: Any, evidence: MergeEvidence) -> None:
        if publication.state not in {"pr_open", "merge_confirmed", "materializing"}:
            raise ReconciliationBlocked("PUBLICATION_STATE_INVALID")
        if not evidence.merged:
            raise ReconciliationBlocked("PUBLICATION_NOT_MERGED")
        if not evidence.commit_id.strip():
            raise ReconciliationBlocked("PUBLICATION_MERGE_COMMIT_MISSING")
        if not _SHA256.fullmatch(evidence.content_hash):
            raise ReconciliationBlocked("PUBLICATION_CONTENT_HASH_INVALID")
        if evidence.content_hash != publication.content_hash:
            raise ReconciliationBlocked("PUBLICATION_CONTENT_HASH_MISMATCH")

    @staticmethod
    def _lease_active(entry: JournalEntry) -> bool:
        try:
            updated_at = datetime.fromisoformat(entry.updated_at)
        except ValueError:
            return False
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=UTC)
        return (datetime.now(UTC) - updated_at).total_seconds() < _EXECUTION_LEASE_SECONDS

    def _materialize_pending(
        self,
        scope: Any,
        publication_id: str,
        steps: Sequence[MaterializationStep],
        entries: Sequence[JournalEntry],
        provenance: Mapping[str, str],
    ) -> None:
        by_position = {step.position: step for step in steps}
        for entry in entries:
            if entry.status in {"completed", "skipped", "compensated"}:
                continue
            step = by_position[entry.position]
            if step.kind == "git_only":
                self._journal.mark(scope, publication_id, entry.position, status="skipped")
                continue
            if not self._journal.claim(scope, publication_id, entry.position):
                raise ReconciliationBlocked("PUBLICATION_JOURNAL_STEP_CONFLICT")
            result = self._materializer.materialize(step, provenance=provenance)
            self._journal.mark(
                scope,
                publication_id,
                entry.position,
                status="completed",
                external_id=str(result.get("name") or step.name),
                version=str(result.get("version") or ""),
            )

    def _attempt_compensation(self, entry: JournalEntry) -> bool:
        try:
            return self._materializer.compensate(entry)
        except Exception:  # noqa: BLE001 - falha externa vira evidência de remediação
            return False

    def _compensate_entry(self, scope: Any, publication_id: str, entry: JournalEntry) -> bool:
        if entry.status == "executing":
            self._journal.mark(
                scope,
                publication_id,
                entry.position,
                status="compensation_required",
                error_code="PUBLICATION_MATERIALIZATION_OUTCOME_UNKNOWN",
            )
            return True
        if entry.status != "completed":
            return False
        compensated = self._attempt_compensation(entry)
        self._journal.mark(
            scope,
            publication_id,
            entry.position,
            status="compensated" if compensated else "compensation_required",
            external_id=entry.external_id,
            version=entry.version,
            error_code="" if compensated else "PUBLICATION_COMPENSATION_FAILED",
        )
        return not compensated

    def _retry_compensation_entry(
        self, scope: Any, publication_id: str, entry: JournalEntry
    ) -> bool:
        if entry.status != "compensation_required":
            return False
        if not entry.version and not entry.external_id:
            return True
        compensated = self._attempt_compensation(entry)
        self._journal.mark(
            scope,
            publication_id,
            entry.position,
            status="compensated" if compensated else "compensation_required",
            external_id=entry.external_id,
            version=entry.version,
            error_code="" if compensated else "PUBLICATION_COMPENSATION_FAILED",
        )
        return not compensated

    def reconcile(
        self, publication: Any, evidence: MergeEvidence, *, scope: Any | None = None,
        operations: Sequence[Mapping[str, Any]] = (),
    ) -> ReconciliationResult:
        self._verify(publication, evidence)
        if self._journal is None or self._publications is None or scope is None:
            legacy_step = MaterializationStep(0, publication.id, "git_only", publication.id, {})
            self._materializer.materialize(legacy_step, provenance={})
            return ReconciliationResult("completed", evidence.commit_id, ())

        steps = materialization_steps(operations)
        self._journal.ensure(scope, publication.id, steps)
        if publication.state != "materializing":
            self._publications.transition_reconciliation(
                scope, publication.id,
                expected_states=("pr_open", "merge_confirmed"),
                state="materializing", step="materialize", commit_id=evidence.commit_id,
                merge_status="merged", now=datetime.now(UTC).isoformat(),
            )
        provenance = {
            "publication_id": publication.id, "changeset_id": publication.changeset_id,
            "revision": str(publication.revision), "content_hash": publication.content_hash,
            "commit_id": evidence.commit_id,
        }
        existing = self._journal.list(scope, publication.id)
        executing = tuple(entry for entry in existing if entry.status == "executing")
        if any(self._lease_active(entry) for entry in executing):
            raise ReconciliationBlocked("PUBLICATION_MATERIALIZATION_BUSY")
        if executing:
            self._compensate(
                scope,
                publication,
                error_code="PUBLICATION_MATERIALIZATION_OUTCOME_UNKNOWN",
            )
            return ReconciliationResult(
                "compensation_required",
                evidence.commit_id,
                self._journal.list(scope, publication.id),
            )
        try:
            self._materialize_pending(
                scope, publication.id, steps, existing, provenance
            )
        except ReconciliationBlocked as exc:
            if str(exc) == "PUBLICATION_JOURNAL_STEP_CONFLICT":
                raise ReconciliationBlocked("PUBLICATION_MATERIALIZATION_BUSY") from exc
            self._compensate(scope, publication, error_code=type(exc).__name__)
            raise
        except Exception as exc:
            self._compensate(scope, publication, error_code=type(exc).__name__)
            raise

        self._publications.transition_reconciliation(
            scope, publication.id, expected_states=("materializing",), state="completed",
            step="completed", now=datetime.now(UTC).isoformat(),
        )
        return ReconciliationResult(
            "completed", evidence.commit_id, self._journal.list(scope, publication.id)
        )

    def _compensate(self, scope: Any, publication: Any, *, error_code: str) -> None:
        self._publications.transition_reconciliation(
            scope, publication.id, expected_states=("materializing",), state="compensating",
            step="compensate", error_code=error_code, now=datetime.now(UTC).isoformat(),
        )
        required = False
        for entry in reversed(self._journal.list(scope, publication.id)):
            required = self._compensate_entry(scope, publication.id, entry) or required
        final_state = "compensation_required" if required else "compensated"
        self._publications.transition_reconciliation(
            scope, publication.id, expected_states=("compensating",), state=final_state,
            step=final_state, error_code=error_code, now=datetime.now(UTC).isoformat(),
        )

    def compensate(self, scope: Any, publication: Any) -> tuple[JournalEntry, ...]:
        if self._journal is None or self._publications is None:
            raise ReconciliationBlocked("PUBLICATION_RECONCILIATION_NOT_CONFIGURED")
        if publication.state != "compensation_required":
            raise ReconciliationBlocked("PUBLICATION_COMPENSATION_STATE_INVALID")
        self._publications.transition_reconciliation(
            scope, publication.id, expected_states=("compensation_required",),
            state="compensating", step="compensate", now=datetime.now(UTC).isoformat(),
        )
        required = False
        for entry in reversed(self._journal.list(scope, publication.id)):
            required = (
                self._retry_compensation_entry(scope, publication.id, entry) or required
            )
        final_state = "compensation_required" if required else "compensated"
        self._publications.transition_reconciliation(
            scope, publication.id, expected_states=("compensating",), state=final_state,
            step=final_state,
            error_code="PUBLICATION_COMPENSATION_FAILED" if required else "",
            now=datetime.now(UTC).isoformat(),
        )
        return self._journal.list(scope, publication.id)
