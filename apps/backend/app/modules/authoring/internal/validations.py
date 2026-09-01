"""Relatórios imutáveis de conformidade por revisão e fase de autoria."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Literal, Protocol
from uuid import uuid4

import app
from app.modules.okf.public import (
    AuthoringInvalid,
    parse_authoring_document,
    spec_references,
)

from .catalog import (
    CatalogSource,
    ResourceNotFound,
    SourceUnavailable,
    resource_detail,
    resource_versions,
)

if TYPE_CHECKING:
    from .changesets import ChangeSetScope, ChangeSetService, StoredChangeSet

ValidationStatus = Literal["approved", "failed", "pending"]
ValidationPhase = Literal["editing", "submission", "approval", "materialization"]
_PHASES = frozenset({"editing", "submission", "approval", "materialization"})


@dataclass(frozen=True, slots=True)
class ValidationCheck:
    id: str
    status: ValidationStatus
    blocking: bool
    source: str
    reason: str
    evidence: Mapping[str, Any]
    severity: Literal["error", "warning", "info"] = "error"

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence", MappingProxyType(dict(self.evidence)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "blocking": self.blocking,
            "source": self.source,
            "reason": self.reason,
            "evidence": dict(self.evidence),
            "severity": self.severity,
        }


@dataclass(frozen=True, slots=True)
class StoredValidationReport:
    id: str
    changeset_id: str
    revision: int
    phase: ValidationPhase
    overall: ValidationStatus
    content_hash: str
    checks: tuple[ValidationCheck, ...]
    actor_id: str
    created_at: str

    @property
    def blocks_transition(self) -> bool:
        return any(check.blocking and check.status != "approved" for check in self.checks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "changeset_id": self.changeset_id,
            "revision": self.revision,
            "phase": self.phase,
            "overall": self.overall,
            "content_hash": self.content_hash,
            "checks": [check.to_dict() for check in self.checks],
            "blocks_transition": self.blocks_transition,
            "actor_id": self.actor_id,
            "created_at": self.created_at,
        }


class ValidationReportNotFound(LookupError):
    """O relatório não existe no tenant e área consultados."""


class ValidationTransitionBlocked(AuthoringInvalid):
    """A fase não possui um relatório atual sem checks bloqueadores."""


class ValidationReportRepository(Protocol):
    def append(
        self, scope: ChangeSetScope, report: StoredValidationReport
    ) -> StoredValidationReport: ...

    def get(
        self, scope: ChangeSetScope, report_id: str
    ) -> StoredValidationReport | None: ...

    def list(
        self,
        scope: ChangeSetScope,
        changeset_id: str,
        *,
        revision: int | None = None,
        phase: ValidationPhase | None = None,
    ) -> list[StoredValidationReport]: ...


class SQLiteValidationReportRepository:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        connection = self._connect()
        try:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS authoring_validation_reports (
                    tenant_id TEXT NOT NULL, area_id TEXT NOT NULL, report_id TEXT NOT NULL,
                    changeset_id TEXT NOT NULL, revision BIGINT NOT NULL, phase TEXT NOT NULL,
                    overall TEXT NOT NULL, content_hash TEXT NOT NULL, checks_json TEXT NOT NULL,
                    actor_oid TEXT NOT NULL, created_at TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, area_id, report_id)
                )"""
            )
            connection.execute(
                """CREATE INDEX IF NOT EXISTS ix_authoring_validation_reports_revision
                   ON authoring_validation_reports
                   (tenant_id, area_id, changeset_id, revision, phase, created_at)"""
            )
            connection.commit()
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path, timeout=5)

    @staticmethod
    def _record(row: tuple[Any, ...]) -> StoredValidationReport:
        return StoredValidationReport(
            id=row[0],
            changeset_id=row[1],
            revision=int(row[2]),
            phase=row[3],
            overall=row[4],
            content_hash=row[5],
            checks=tuple(ValidationCheck(**check) for check in json.loads(row[6])),
            actor_id=row[7],
            created_at=row[8],
        )

    def append(
        self, scope: ChangeSetScope, report: StoredValidationReport
    ) -> StoredValidationReport:
        connection = self._connect()
        try:
            connection.execute(
                """INSERT INTO authoring_validation_reports
                   (tenant_id, area_id, report_id, changeset_id, revision, phase, overall,
                    content_hash, checks_json, actor_oid, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    scope.tenant_id,
                    scope.area_id,
                    report.id,
                    report.changeset_id,
                    report.revision,
                    report.phase,
                    report.overall,
                    report.content_hash,
                    json.dumps(
                        [check.to_dict() for check in report.checks],
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    scope.actor_id,
                    report.created_at,
                ),
            )
            connection.commit()
            return report
        finally:
            connection.close()

    def get(
        self, scope: ChangeSetScope, report_id: str
    ) -> StoredValidationReport | None:
        connection = self._connect()
        try:
            row = connection.execute(
                """SELECT report_id, changeset_id, revision, phase, overall, content_hash,
                          checks_json, actor_oid, created_at
                   FROM authoring_validation_reports
                   WHERE tenant_id = ? AND area_id = ? AND report_id = ?""",
                (scope.tenant_id, scope.area_id, report_id),
            ).fetchone()
            return self._record(row) if row is not None else None
        finally:
            connection.close()

    def list(
        self,
        scope: ChangeSetScope,
        changeset_id: str,
        *,
        revision: int | None = None,
        phase: ValidationPhase | None = None,
    ) -> list[StoredValidationReport]:
        clauses = ["tenant_id = ?", "area_id = ?", "changeset_id = ?"]
        parameters: list[Any] = [scope.tenant_id, scope.area_id, changeset_id]
        if revision is not None:
            clauses.append("revision = ?")
            parameters.append(revision)
        if phase is not None:
            clauses.append("phase = ?")
            parameters.append(phase)
        connection = self._connect()
        try:
            rows = connection.execute(
                """SELECT report_id, changeset_id, revision, phase, overall, content_hash,
                          checks_json, actor_oid, created_at
                   FROM authoring_validation_reports WHERE """
                + " AND ".join(clauses)
                + " ORDER BY created_at DESC, report_id DESC",
                parameters,
            ).fetchall()
            return [self._record(row) for row in rows]
        finally:
            connection.close()


class ValidationService:
    def __init__(
        self,
        changesets: ChangeSetService,
        repository: ValidationReportRepository,
        *,
        sources: tuple[CatalogSource, ...],
        now: Callable[[], str] | None = None,
    ) -> None:
        self._changesets = changesets
        self._repository = repository
        self._sources = sources
        self._now = now or (lambda: datetime.now(UTC).isoformat())

    @staticmethod
    def _documents(record: StoredChangeSet) -> list[Any]:
        return [
            parse_authoring_document(
                operation["document"], where=f"changeset:{record.id}:{index}"
            )
            for index, operation in enumerate(record.content["operations"])
            if operation.get("document") is not None
        ]

    @staticmethod
    def _version_values(value: Any) -> set[str]:
        if isinstance(value, Mapping):
            return {
                token
                for key in ("version", "id", "name")
                for token in ValidationService._version_values(value.get(key))
            }
        if isinstance(value, (str, int)) and not isinstance(value, bool):
            return {str(value)}
        return set()

    def _classify_reference(
        self,
        reference: Any,
        internal: set[tuple[str, str, str]],
        phase: ValidationPhase,
    ) -> Literal["internal", "deferred", "resolved", "unresolved", "unverifiable"]:
        if (reference.type, reference.id, reference.revision) in internal:
            return "internal"
        if phase in {"editing", "submission"}:
            return "deferred"
        try:
            detail = resource_detail(reference.type, reference.id, sources=self._sources)
        except ResourceNotFound:
            return "unresolved"
        except SourceUnavailable:
            return "unverifiable"
        if reference.revision is None:
            return "resolved"
        try:
            versions = resource_versions(
                reference.type, reference.id, sources=self._sources, limit=100
            )
        except SourceUnavailable:
            return "unverifiable"
        candidates = self._version_values(
            (detail.get("definition") or {}).get("version")
        )
        for item in versions["items"]:
            candidates.update(self._version_values(item))
        if versions["state"] == "unavailable" and not candidates:
            return "unverifiable"
        if reference.revision not in candidates:
            return "unresolved"
        return "resolved"

    def _reference_check(
        self,
        documents: list[Any],
        phase: ValidationPhase,
    ) -> ValidationCheck:
        internal = {
            (document.type, document.id, document.revision) for document in documents
        }
        references = [
            reference
            for document in documents
            for reference in spec_references(
                document.type, dict(document.spec), where=f"{document.type}:{document.id}"
            )
        ]
        classifications = [
            self._classify_reference(reference, internal, phase)
            for reference in references
        ]
        unresolved = classifications.count("unresolved")
        deferred = classifications.count("deferred")
        unverifiable = classifications.count("unverifiable")
        status: ValidationStatus = "approved"
        reason = "Referências verificadas contra a revisão e o catálogo factual."
        if deferred or unverifiable:
            status = "pending"
            reason = (
                "A fonte não expôs versão suficiente para confirmar a referência."
                if unverifiable
                else "Referências externas adiadas para a fase que exige a fonte dona."
            )
        if unresolved:
            status = "failed"
            reason = "Há referências obrigatórias não resolvidas."
        return ValidationCheck(
            id="references",
            status=status,
            blocking=unresolved > 0
            or (unverifiable > 0 and phase in {"approval", "materialization"}),
            source="local",
            reason=reason,
            evidence={
                "total": len(references),
                "internal": classifications.count("internal"),
                "resolvedExternal": classifications.count("resolved"),
                "deferred": deferred,
                "unverifiable": unverifiable,
                "unresolved": unresolved,
            },
            severity="warning" if status == "pending" else "error",
        )

    @staticmethod
    def _redacted_count(value: Any) -> int:
        if isinstance(value, Mapping):
            return sum(ValidationService._redacted_count(item) for item in value.values())
        if isinstance(value, (list, tuple)):
            return sum(ValidationService._redacted_count(item) for item in value)
        return int(value == "<redacted>")

    @staticmethod
    def _mcp_check(
        documents: list[Any], phase: ValidationPhase
    ) -> ValidationCheck:
        bindings = [document for document in documents if document.type == "mcp-binding"]
        if phase not in {"approval", "materialization"} or not bindings:
            return ValidationCheck(
                "mcp-conformity",
                "approved",
                False,
                "local",
                "Nenhum binding MCP exige avaliação nesta fase.",
                {"bindings": len(bindings), "executed": 0},
                "info",
            )
        from app.modules.platform_ops.public import (
            ConformityNotFound,
            evaluate_mcp_binding,
        )

        decisions: list[str] = []
        try:
            for document in bindings:
                result = evaluate_mcp_binding(dict(document.spec))
                decisions.append(str(result["status"]))
        except ConformityNotFound:
            return ValidationCheck(
                "mcp-conformity",
                "failed",
                True,
                "local",
                "Uma referência MCP não existe no escopo atual.",
                {"bindings": len(bindings), "executed": len(decisions)},
            )
        except Exception:  # noqa: BLE001 - indisponibilidade externa nunca vira aprovação
            return ValidationCheck(
                "mcp-conformity",
                "pending",
                True,
                "azure",
                "A fonte MCP necessária à avaliação está indisponível.",
                {"bindings": len(bindings), "executed": len(decisions)},
                "warning",
            )
        blocked = decisions.count("block")
        return ValidationCheck(
            "mcp-conformity",
            "failed" if blocked else "approved",
            True,
            "local",
            "Bindings MCP avaliados pelo motor de conformidade existente.",
            {"bindings": len(bindings), "executed": len(decisions), "blocked": blocked},
        )

    def _checks(
        self, record: StoredChangeSet, phase: ValidationPhase
    ) -> tuple[ValidationCheck, ...]:
        documents = self._documents(record)
        policy_documents = [document for document in documents if document.type == "policy"]
        redacted = self._redacted_count(record.content)
        scoped = all(
            document.tenant and document.area for document in documents
        )
        gaps = record.content.get("gaps", ())
        return (
            ValidationCheck(
                "schema",
            "approved" if documents else "failed",
                True,
                "local",
                "Todos os documentos foram parseados pelo perfil de autoria registrado.",
                {
                    "documents": len(documents),
                    "contentHash": record.content_hash,
                    "validator": "x-foundry-authoring",
                },
            ),
            ValidationCheck(
                "invariants",
                "approved" if scoped else "failed",
                True,
                "local",
                "Escopo e identidade declarativos foram verificados.",
                {"scopedDocuments": sum(bool(item.tenant and item.area) for item in documents)},
            ),
            self._reference_check(documents, phase),
            ValidationCheck(
                "sensitive-data",
                "failed" if redacted else "approved",
                phase in {"submission", "approval", "materialization"},
                "local",
                "Nenhum valor sensível redigido está presente."
                if not redacted
                else "A revisão continha valores sensíveis e não pode avançar.",
                {"redactedValues": redacted},
            ),
            ValidationCheck(
                "gaps",
                "failed" if gaps else "approved",
                phase in {"approval", "materialization"},
                "local",
                "Nenhuma lacuna bloqueadora foi declarada."
                if not gaps
                else "A revisão possui lacunas declaradas que exigem resolução.",
                {"count": len(gaps)},
            ),
            ValidationCheck(
                "authorization",
                "approved",
                phase in {"submission", "approval", "materialization"},
                "local",
                "Declarações de escrita, aprovação e negação passaram pelo schema OKF.",
                {"declarativeDocuments": len(documents)},
            ),
            ValidationCheck(
                "policies",
                "approved",
                phase in {"approval", "materialization"},
                "local",
                "Policies declaradas exigem enforcement externo e fontes nomeadas.",
                {"policies": len(policy_documents)},
            ),
            self._mcp_check(documents, phase),
            ValidationCheck(
                "azure-readiness",
                "pending",
                phase == "materialization",
                "azure",
                "Readiness oficial depende de execução autenticada no Azure.",
                {"executed": False, "adapter": "local"},
                "info",
            ),
        )

    def run(
        self,
        scope: ChangeSetScope,
        changeset_id: str,
        *,
        revision: int,
        phase: ValidationPhase,
    ) -> StoredValidationReport:
        if phase not in _PHASES:
            raise AuthoringInvalid("VALIDATION_PHASE_INVALID")
        record = self._changesets.get_revision(scope, changeset_id, revision)
        checks = self._checks(record, phase)
        overall: ValidationStatus = "approved"
        if any(check.status == "pending" for check in checks):
            overall = "pending"
        if any(check.status == "failed" for check in checks):
            overall = "failed"
        report = StoredValidationReport(
            id=str(uuid4()),
            changeset_id=record.id,
            revision=record.revision,
            phase=phase,
            overall=overall,
            content_hash=record.content_hash,
            checks=checks,
            actor_id=scope.actor_id,
            created_at=self._now(),
        )
        return self._repository.append(scope, report)

    def get(self, scope: ChangeSetScope, report_id: str) -> StoredValidationReport:
        report = self._repository.get(scope, report_id)
        if report is None:
            raise ValidationReportNotFound("VALIDATION_REPORT_NOT_FOUND")
        return report

    def list(
        self,
        scope: ChangeSetScope,
        changeset_id: str,
        *,
        revision: int | None = None,
        phase: ValidationPhase | None = None,
    ) -> list[StoredValidationReport]:
        self._changesets.get(scope, changeset_id)
        return self._repository.list(
            scope, changeset_id, revision=revision, phase=phase
        )

    def assert_transition(
        self,
        scope: ChangeSetScope,
        changeset_id: str,
        *,
        phase: ValidationPhase,
    ) -> StoredValidationReport:
        current = self._changesets.get(scope, changeset_id)
        reports = self.list(
            scope, changeset_id, revision=current.revision, phase=phase
        )
        if not reports:
            raise ValidationTransitionBlocked("VALIDATION_REPORT_REQUIRED")
        report = reports[0]
        if report.content_hash != current.content_hash or report.blocks_transition:
            raise ValidationTransitionBlocked("VALIDATION_TRANSITION_BLOCKED")
        return report


_default_service: ValidationService | None = None


def default_validation_service() -> ValidationService:
    global _default_service
    if _default_service is None:
        from .changesets import default_changeset_service
        from .sources import default_sources

        data_directory = Path(app.__file__).resolve().parent.parent / "data"
        _default_service = ValidationService(
            default_changeset_service(),
            SQLiteValidationReportRepository(data_directory / "authoring.sqlite3"),
            sources=default_sources(),
        )
    return _default_service
