"""Decisões humanas imutáveis presas à revisão exata de um ChangeSet."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Protocol
from uuid import uuid4

import app
from app.modules.okf.public import AuthoringInvalid

if TYPE_CHECKING:
    from .changesets import ChangeSetScope, ChangeSetService
    from .validations import ValidationService

DecisionType = Literal["approve", "reject"]


class DecisionConflict(AuthoringInvalid):
    """A decisão não corresponde ao estado, revisão ou conteúdo atuais."""


class DecisionNotFound(AuthoringInvalid):
    """A decisão não existe no escopo consultado."""


@dataclass(frozen=True, slots=True)
class StoredDecision:
    id: str
    changeset_id: str
    revision: int
    content_hash: str
    decision: DecisionType
    reason: str
    approver_id: str
    roles: tuple[str, ...]
    audit_ref: str
    correlation_id: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "changeset_id": self.changeset_id,
            "revision": self.revision,
            "content_hash": self.content_hash,
            "decision": self.decision,
            "reason": self.reason,
            "approver_id": self.approver_id,
            "roles": list(self.roles),
            "audit_ref": self.audit_ref,
            "correlation_id": self.correlation_id,
            "created_at": self.created_at,
        }


class DecisionRepository(Protocol):
    def append(
        self, scope: ChangeSetScope, decision: StoredDecision
    ) -> StoredDecision: ...

    def get(
        self, scope: ChangeSetScope, decision_id: str
    ) -> StoredDecision | None: ...

    def list(
        self, scope: ChangeSetScope, changeset_id: str
    ) -> list[StoredDecision]: ...


class SQLiteDecisionRepository:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        connection = self._connect()
        try:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS authoring_decisions (
                    tenant_id TEXT NOT NULL, area_id TEXT NOT NULL,
                    decision_id TEXT NOT NULL, changeset_id TEXT NOT NULL,
                    revision BIGINT NOT NULL, content_hash TEXT NOT NULL,
                    decision TEXT NOT NULL, reason TEXT NOT NULL,
                    approver_oid TEXT NOT NULL, roles_json TEXT NOT NULL,
                    audit_ref TEXT NOT NULL, correlation_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, area_id, decision_id),
                    UNIQUE (tenant_id, area_id, changeset_id, revision)
                )"""
            )
            connection.execute(
                """CREATE INDEX IF NOT EXISTS ix_authoring_decisions_changeset
                   ON authoring_decisions
                   (tenant_id, area_id, changeset_id, revision, created_at)"""
            )
            connection.commit()
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path, timeout=5)

    @staticmethod
    def _record(row: tuple[Any, ...]) -> StoredDecision:
        import json

        return StoredDecision(
            id=row[0],
            changeset_id=row[1],
            revision=int(row[2]),
            content_hash=row[3],
            decision=row[4],
            reason=row[5],
            approver_id=row[6],
            roles=tuple(json.loads(row[7])),
            audit_ref=row[8],
            correlation_id=row[9],
            created_at=row[10],
        )

    def append(
        self, scope: ChangeSetScope, decision: StoredDecision
    ) -> StoredDecision:
        import json

        connection = self._connect()
        try:
            cursor = connection.cursor()
            cursor.execute("BEGIN IMMEDIATE")
            state = "approved" if decision.decision == "approve" else "rejected"
            changed = cursor.execute(
                """UPDATE authoring_changesets SET state = ?, updated_at = ?
                   WHERE tenant_id = ? AND area_id = ? AND changeset_id = ?
                     AND state = 'submitted' AND current_revision = ?
                     AND EXISTS (
                       SELECT 1 FROM authoring_changeset_revisions r
                       WHERE r.tenant_id = authoring_changesets.tenant_id
                         AND r.area_id = authoring_changesets.area_id
                         AND r.changeset_id = authoring_changesets.changeset_id
                         AND r.revision = authoring_changesets.current_revision
                         AND r.content_hash = ?
                     )""",
                (
                    state,
                    decision.created_at,
                    scope.tenant_id,
                    scope.area_id,
                    decision.changeset_id,
                    decision.revision,
                    decision.content_hash,
                ),
            ).rowcount
            if changed != 1:
                raise DecisionConflict("DECISION_CONTENT_STALE")
            cursor.execute(
                """UPDATE authoring_changeset_revisions SET state = ?
                   WHERE tenant_id = ? AND area_id = ? AND changeset_id = ?
                     AND revision = ? AND content_hash = ?""",
                (
                    state,
                    scope.tenant_id,
                    scope.area_id,
                    decision.changeset_id,
                    decision.revision,
                    decision.content_hash,
                ),
            )
            cursor.execute(
                """INSERT INTO authoring_decisions
                   (tenant_id, area_id, decision_id, changeset_id, revision,
                    content_hash, decision, reason, approver_oid, roles_json,
                    audit_ref, correlation_id, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    scope.tenant_id,
                    scope.area_id,
                    decision.id,
                    decision.changeset_id,
                    decision.revision,
                    decision.content_hash,
                    decision.decision,
                    decision.reason,
                    scope.actor_id,
                    json.dumps(decision.roles, separators=(",", ":")),
                    decision.audit_ref,
                    decision.correlation_id,
                    decision.created_at,
                ),
            )
            connection.commit()
            return decision
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise DecisionConflict("DECISION_ALREADY_RECORDED") from exc
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get(
        self, scope: ChangeSetScope, decision_id: str
    ) -> StoredDecision | None:
        connection = self._connect()
        try:
            row = connection.execute(
                """SELECT decision_id, changeset_id, revision, content_hash,
                          decision, reason, approver_oid, roles_json, audit_ref,
                          correlation_id, created_at
                   FROM authoring_decisions
                   WHERE tenant_id = ? AND area_id = ? AND decision_id = ?""",
                (scope.tenant_id, scope.area_id, decision_id),
            ).fetchone()
            return self._record(row) if row is not None else None
        finally:
            connection.close()

    def list(
        self, scope: ChangeSetScope, changeset_id: str
    ) -> list[StoredDecision]:
        connection = self._connect()
        try:
            rows = connection.execute(
                """SELECT decision_id, changeset_id, revision, content_hash,
                          decision, reason, approver_oid, roles_json, audit_ref,
                          correlation_id, created_at
                   FROM authoring_decisions
                   WHERE tenant_id = ? AND area_id = ? AND changeset_id = ?
                   ORDER BY revision DESC, created_at DESC""",
                (scope.tenant_id, scope.area_id, changeset_id),
            ).fetchall()
            return [self._record(row) for row in rows]
        finally:
            connection.close()


class DecisionService:
    def __init__(
        self,
        changesets: ChangeSetService,
        validations: ValidationService,
        repository: DecisionRepository,
        *,
        audit_recorder: Callable[..., dict[str, Any]] | None = None,
        now: Callable[[], str] | None = None,
    ) -> None:
        self._changesets = changesets
        self._validations = validations
        self._repository = repository
        self._audit_recorder = audit_recorder or self._record_audit
        self._now = now or (lambda: datetime.now(UTC).isoformat())

    @staticmethod
    def _reason(reason: str) -> str:
        if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 1000:
            raise AuthoringInvalid("DECISION_REASON_INVALID")
        from app.modules.audit.public import redact

        redacted, _matches = redact(reason.strip())
        return redacted

    @staticmethod
    def _record_audit(**event: Any) -> dict[str, Any]:
        from app.modules.audit.public import record

        return record(**event)

    def decide(
        self,
        scope: ChangeSetScope,
        changeset_id: str,
        *,
        revision: int,
        content_hash: str,
        decision: DecisionType,
        reason: str,
        roles: set[str],
        correlation_id: str | None = None,
    ) -> StoredDecision:
        if decision not in {"approve", "reject"}:
            raise AuthoringInvalid("DECISION_TYPE_INVALID")
        if roles != {"Approver"} and "Approver" not in roles:
            raise DecisionConflict("APPROVER_REQUIRED")
        if not isinstance(content_hash, str) or len(content_hash) != 64:
            raise AuthoringInvalid("DECISION_CONTENT_HASH_INVALID")
        current = self._changesets.get(scope, changeset_id)
        if (
            current.state != "submitted"
            or current.revision != revision
            or current.content_hash != content_hash
        ):
            raise DecisionConflict("DECISION_CONTENT_STALE")
        if decision == "approve":
            self._validations.assert_transition(
                scope, changeset_id, phase="approval"
            )
        safe_reason = self._reason(reason)
        correlation = correlation_id or uuid4().hex
        created_at = self._now()
        try:
            event = self._audit_recorder(
                scope=f"authoring:{scope.tenant_id}:{scope.area_id}",
                actor=scope.actor_id,
                kind="approval",
                summary=f"{decision} em ChangeSet",
                ref=changeset_id,
                detail={
                    "decision": decision,
                    "revision": revision,
                    "content_hash": content_hash,
                    "correlation_id": correlation,
                    "has_reason": True,
                    "reason_chars": len(safe_reason),
                },
            )
        except Exception as exc:
            raise DecisionConflict("DECISION_AUDIT_REQUIRED") from exc
        audit_ref = str(event.get("hash") or "")
        if not audit_ref:
            raise DecisionConflict("DECISION_AUDIT_REQUIRED")
        stored = StoredDecision(
            id=str(uuid4()),
            changeset_id=changeset_id,
            revision=revision,
            content_hash=content_hash,
            decision=decision,
            reason=safe_reason,
            approver_id=scope.actor_id,
            roles=tuple(sorted(roles)),
            audit_ref=audit_ref,
            correlation_id=correlation,
            created_at=created_at,
        )
        return self._repository.append(scope, stored)

    def get(self, scope: ChangeSetScope, decision_id: str) -> StoredDecision:
        decision = self._repository.get(scope, decision_id)
        if decision is None:
            raise DecisionNotFound("DECISION_NOT_FOUND")
        return decision

    def list(
        self, scope: ChangeSetScope, changeset_id: str
    ) -> list[StoredDecision]:
        self._changesets.get(scope, changeset_id)
        return self._repository.list(scope, changeset_id)

    def assert_approved(
        self, scope: ChangeSetScope, changeset_id: str
    ) -> StoredDecision:
        current = self._changesets.get(scope, changeset_id)
        decisions = self.list(scope, changeset_id)
        match = next(
            (
                item
                for item in decisions
                if item.decision == "approve"
                and item.revision == current.revision
                and item.content_hash == current.content_hash
            ),
            None,
        )
        if current.state != "approved" or match is None:
            raise DecisionConflict("APPROVAL_REQUIRED")
        return match


_default_service: DecisionService | None = None


def default_decision_service() -> DecisionService:
    global _default_service
    if _default_service is None:
        from .changesets import default_changeset_service
        from .validations import default_validation_service

        data_directory = Path(app.__file__).resolve().parent.parent / "data"
        database = data_directory / "authoring.sqlite3"
        _default_service = DecisionService(
            default_changeset_service(),
            default_validation_service(),
            SQLiteDecisionRepository(database),
        )
    return _default_service
