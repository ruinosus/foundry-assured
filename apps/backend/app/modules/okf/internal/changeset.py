"""Proposta efêmera e autorizada de mudanças multi-documento OKF."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import InitVar, dataclass, replace
from hashlib import sha256
from types import MappingProxyType
from typing import Any

from .authoring import OPERATIONS, copilot_allows
from .catalog import AuthoringCatalog
from .envelope import AuthoringDocument, AuthoringInvalid
from .schemas import spec_references

_IDENTIFIER = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_REVIEW_TOKEN = object()
_CONFIRM_TOKEN = object()


class ChangeSetInvalid(AuthoringInvalid):
    """A proposta não forma um conjunto coerente e autorizado."""


def _text(value: str, *, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ChangeSetInvalid(f"{where}: deve ser texto não vazio")
    return value.strip()


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(child) for key, child in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(child) for child in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(child) for key, child in value.items()}
    if isinstance(value, tuple):
        return [_thaw(child) for child in value]
    return value


def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, Mapping):
        flattened: dict[str, Any] = {}
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            flattened.update(_flatten(child, path))
        return flattened
    return {prefix: value}


@dataclass(frozen=True, slots=True)
class ChangeEvidence:
    """Fonte declarada para um campo proposto."""

    field: str
    source: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "field", _text(self.field, where="evidence.field"))
        object.__setattr__(self, "source", _text(self.source, where="evidence.source"))


@dataclass(frozen=True, slots=True)
class ChangeGap:
    """Capacidade ausente, separada das referências disponíveis."""

    capability: str
    reason: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "capability", _text(self.capability, where="gap.capability"))
        object.__setattr__(self, "reason", _text(self.reason, where="gap.reason"))


@dataclass(frozen=True, slots=True)
class ChangeDecision:
    """Decisão humana sobre um documento da proposta."""

    operation_id: str
    decision: str
    edited_document: AuthoringDocument | None = None
    edited_evidence: tuple[ChangeEvidence, ...] = ()

    def __post_init__(self) -> None:
        if self.decision not in {"accept", "edit", "discard"}:
            raise ChangeSetInvalid(f"decision {self.operation_id}: decisão desconhecida")
        if self.decision == "edit" and self.edited_document is None:
            raise ChangeSetInvalid(f"decision {self.operation_id}: edit exige documento")
        if self.decision != "edit" and self.edited_document is not None:
            raise ChangeSetInvalid(
                f"decision {self.operation_id}: documento editado só é aceito com decisão edit"
            )
        object.__setattr__(self, "edited_evidence", tuple(self.edited_evidence))
        if self.decision == "edit" and not self.edited_evidence:
            raise ChangeSetInvalid(f"decision {self.operation_id}: edit exige nova evidência")
        if self.decision != "edit" and self.edited_evidence:
            raise ChangeSetInvalid(
                f"decision {self.operation_id}: evidência editada só é aceita com decisão edit"
            )


@dataclass(frozen=True, slots=True)
class DocumentDiff:
    """Antes/depois estruturado de uma operação, pronto para renderização."""

    operation_id: str
    operation: str
    before: Mapping[str, Any] | None
    after: Mapping[str, Any]
    changes: tuple[FieldChange, ...]
    summary: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "before", _freeze(self.before))
        object.__setattr__(self, "after", _freeze(self.after))
        object.__setattr__(self, "changes", tuple(self.changes))


@dataclass(frozen=True, slots=True)
class FieldChange:
    """Alteração estruturada de um path do documento."""

    path: str
    kind: str
    before: Any = None
    after: Any = None

    def __post_init__(self) -> None:
        if self.kind not in {"add", "remove", "replace"}:
            raise ChangeSetInvalid(f"patch {self.path}: operação desconhecida")
        object.__setattr__(self, "before", _freeze(self.before))
        object.__setattr__(self, "after", _freeze(self.after))


@dataclass(frozen=True, slots=True)
class ReviewedChangeSet:
    """ChangeSet integralmente validado após decisão humana por documento."""

    changeset: OkfChangeSet
    _token: InitVar[object | None]

    def __post_init__(self, _token: object | None) -> None:
        if _token is not _REVIEW_TOKEN:
            raise ChangeSetInvalid("ReviewedChangeSet só pode nascer de OkfChangeSet.review()")

    def confirm(
        self,
        base_documents: Iterable[AuthoringDocument] = (),
        *,
        current_version: str,
    ) -> ConfirmedChangeSet:
        """Revalida e identifica exatamente o conjunto revisado pela pessoa."""
        baseline = tuple(base_documents)
        self.changeset.validate(baseline, current_version=current_version)
        canonical = json.dumps(
            self.changeset.to_dict(baseline, current_version=current_version),
            sort_keys=True,
            separators=(",", ":"),
        )
        return ConfirmedChangeSet(
            self,
            sha256(canonical.encode("utf-8")).hexdigest(),
            _CONFIRM_TOKEN,
        )


@dataclass(frozen=True, slots=True)
class ConfirmedChangeSet:
    """Confirmação do conjunto normalizado; ainda não publica nada."""

    reviewed: ReviewedChangeSet
    digest: str
    _token: InitVar[object | None]

    def __post_init__(self, _token: object | None) -> None:
        if _token is not _CONFIRM_TOKEN:
            raise ChangeSetInvalid(
                "ConfirmedChangeSet só pode nascer de ReviewedChangeSet.confirm()"
            )


@dataclass(frozen=True, slots=True)
class ChangeOperation:
    """Uma criação, revisão ou depreciação dentro da proposta."""

    id: str
    operation: str
    document: AuthoringDocument
    justification: str
    base_revision: str | None = None
    depends_on: tuple[str, ...] = ()
    evidence: tuple[ChangeEvidence, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not _IDENTIFIER.fullmatch(self.id):
            raise ChangeSetInvalid("operation.id: identificador inválido")
        if self.operation not in OPERATIONS:
            raise ChangeSetInvalid(f"operation {self.id}: operação desconhecida: {self.operation!r}")
        object.__setattr__(
            self,
            "justification",
            _text(self.justification, where=f"operation {self.id}.justification"),
        )
        object.__setattr__(self, "depends_on", tuple(self.depends_on))
        object.__setattr__(self, "evidence", tuple(self.evidence))
        if not self.evidence:
            raise ChangeSetInvalid(f"operation {self.id}: exige evidência por campo e fonte")
        evidence_fields = [item.field for item in self.evidence]
        if len(set(evidence_fields)) != len(evidence_fields):
            raise ChangeSetInvalid(f"operation {self.id}: evidência duplicada para o mesmo campo")


@dataclass(frozen=True, slots=True)
class OkfChangeSet:
    """Conjunto efêmero validado por inteiro antes de qualquer publicação."""

    id: str
    base_version: str
    proposer: AuthoringDocument
    operations: tuple[ChangeOperation, ...]
    justification: str
    gaps: tuple[ChangeGap, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not _IDENTIFIER.fullmatch(self.id):
            raise ChangeSetInvalid("changeset.id: identificador inválido")
        object.__setattr__(self, "base_version", _text(self.base_version, where="changeset.base_version"))
        if self.proposer.type != "copilot":
            raise ChangeSetInvalid("changeset.proposer: deve ser um documento `copilot`")
        if not self.operations:
            raise ChangeSetInvalid("changeset.operations: deve conter ao menos uma operação")
        object.__setattr__(self, "operations", tuple(self.operations))
        object.__setattr__(self, "gaps", tuple(self.gaps))
        object.__setattr__(
            self,
            "justification",
            _text(self.justification, where="changeset.justification"),
        )

    def validate(
        self,
        base_documents: Iterable[AuthoringDocument] = (),
        *,
        current_version: str,
    ) -> None:
        """Valida autorização, versões, dependências e o grafo final de referências."""
        if self.base_version != _text(current_version, where="changeset.current_version"):
            raise ChangeSetInvalid(
                f"changeset.base_version: esperada {current_version!r}, recebida {self.base_version!r}"
            )
        baseline = tuple(base_documents)
        operation_ids = {operation.id for operation in self.operations}
        if len(operation_ids) != len(self.operations):
            raise ChangeSetInvalid("changeset.operations: identificador de operação duplicado")

        proposed_keys: set[tuple[str, str, str, str, str]] = set()
        for operation in self.operations:
            self._validate_operation(operation, operation_ids, baseline)
            key = (*operation.document.identity, operation.document.revision)
            if key in proposed_keys:
                raise ChangeSetInvalid(f"operation {operation.id}: revisão duplicada no ChangeSet")
            proposed_keys.add(key)

        self._validate_dependencies()
        try:
            AuthoringCatalog((*baseline, *(operation.document for operation in self.operations)))
        except AuthoringInvalid as exc:
            raise ChangeSetInvalid(f"changeset.references: {exc}") from exc

    def review(
        self,
        decisions: Iterable[ChangeDecision],
        base_documents: Iterable[AuthoringDocument] = (),
        *,
        current_version: str,
    ) -> ReviewedChangeSet | None:
        """Aplica uma decisão por documento; descartar todos encerra a proposta sem resíduo."""
        baseline = tuple(base_documents)
        self.validate(baseline, current_version=current_version)
        by_operation: dict[str, ChangeDecision] = {}
        for decision in decisions:
            if decision.operation_id in by_operation:
                raise ChangeSetInvalid(f"decision {decision.operation_id}: decisão duplicada")
            by_operation[decision.operation_id] = decision
        expected = {operation.id for operation in self.operations}
        if set(by_operation) != expected:
            raise ChangeSetInvalid("changeset.review: exige uma decisão para cada operação")

        reviewed: list[ChangeOperation] = []
        for operation in self.operations:
            decision = by_operation[operation.id]
            if decision.decision == "discard":
                continue
            if decision.decision == "edit":
                reviewed.append(
                    replace(
                        operation,
                        document=decision.edited_document,
                        evidence=decision.edited_evidence,
                    )
                )
            else:
                reviewed.append(operation)
        if not reviewed:
            return None
        reviewed = OkfChangeSet(
            id=self.id,
            base_version=self.base_version,
            proposer=self.proposer,
            operations=tuple(reviewed),
            justification=self.justification,
            gaps=self.gaps,
        )
        reviewed.validate(baseline, current_version=current_version)
        return ReviewedChangeSet(reviewed, _REVIEW_TOKEN)

    def diffs(
        self,
        base_documents: Iterable[AuthoringDocument] = (),
        *,
        current_version: str,
    ) -> tuple[DocumentDiff, ...]:
        """Produz antes/depois estruturado sem aplicar patch ou persistir documentos."""
        baseline = tuple(base_documents)
        self.validate(baseline, current_version=current_version)
        by_revision = {
            (*document.identity, document.revision): document for document in baseline
        }
        result: list[DocumentDiff] = []
        for operation in self.operations:
            before = None
            if operation.base_revision is not None:
                previous = by_revision.get(
                    (*operation.document.identity, operation.base_revision)
                )
                before = previous.frontmatter() if previous is not None else None
            after = operation.document.frontmatter()
            changes = self._field_changes(before, after)
            counts = {
                kind: sum(change.kind == kind for change in changes)
                for kind in ("add", "remove", "replace")
            }
            result.append(
                DocumentDiff(
                    operation_id=operation.id,
                    operation=operation.operation,
                    before=before,
                    after=after,
                    changes=changes,
                    summary=(
                        f"{operation.operation} {operation.document.type}/"
                        f"{operation.document.id}@{operation.document.revision}: "
                        f"{counts['add']} adicionado(s), {counts['remove']} removido(s), "
                        f"{counts['replace']} alterado(s)"
                    ),
                )
            )
        return tuple(result)

    def to_dict(
        self,
        base_documents: Iterable[AuthoringDocument] = (),
        *,
        current_version: str,
    ) -> dict[str, Any]:
        """Representação estruturada para transporte JSON/YAML."""
        diffs = {
            item.operation_id: item
            for item in self.diffs(base_documents, current_version=current_version)
        }
        return {
            "id": self.id,
            "base_version": self.base_version,
            "justification": self.justification,
            "proposer": {
                "type": self.proposer.type,
                "id": self.proposer.id,
                "revision": self.proposer.revision,
            },
            "operations": [
                {
                    "id": operation.id,
                    "operation": operation.operation,
                    "base_revision": operation.base_revision,
                    "depends_on": list(operation.depends_on),
                    "justification": operation.justification,
                    "evidence": [
                        {"field": item.field, "source": item.source}
                        for item in operation.evidence
                    ],
                    "document": {
                        "frontmatter": operation.document.frontmatter(),
                        "body": operation.document.body,
                    },
                    "patch": [
                        {
                            "path": change.path,
                            "operation": change.kind,
                            "before": _thaw(change.before),
                            "after": _thaw(change.after),
                        }
                        for change in diffs[operation.id].changes
                    ],
                }
                for operation in self.operations
            ],
            "gaps": [
                {"capability": gap.capability, "reason": gap.reason}
                for gap in self.gaps
            ],
        }

    def render_review(
        self,
        base_documents: Iterable[AuthoringDocument] = (),
        *,
        current_version: str,
    ) -> str:
        """Renderiza o resumo humano somente na borda de revisão."""
        baseline = tuple(base_documents)
        self.validate(baseline, current_version=current_version)
        lines = [f"# ChangeSet {self.id}", "", self.justification, "", "## Operações"]
        for item in self.diffs(baseline, current_version=current_version):
            lines.append(f"- `{item.operation_id}`: {item.summary}")
        if self.gaps:
            lines.extend(("", "## Lacunas"))
            lines.extend(f"- **{gap.capability}:** {gap.reason}" for gap in self.gaps)
        return "\n".join(lines) + "\n"

    def _validate_operation(
        self,
        operation: ChangeOperation,
        operation_ids: set[str],
        baseline: tuple[AuthoringDocument, ...],
    ) -> None:
        document = operation.document
        if (document.tenant, document.area) != (self.proposer.tenant, self.proposer.area):
            raise ChangeSetInvalid(f"operation {operation.id}: documento fora do tenant/área do copiloto")
        if not copilot_allows(self.proposer, document.type, operation.operation):
            raise ChangeSetInvalid(f"operation {operation.id}: operação não autorizada pelo copiloto")
        unknown_dependencies = set(operation.depends_on) - operation_ids
        if unknown_dependencies:
            raise ChangeSetInvalid(
                f"operation {operation.id}: dependências inexistentes: {', '.join(sorted(unknown_dependencies))}"
            )
        if operation.id in operation.depends_on:
            raise ChangeSetInvalid(f"operation {operation.id}: dependência circular")
        current = [candidate for candidate in baseline if candidate.identity == document.identity]
        previous = next(
            (
                candidate
                for candidate in current
                if candidate.revision == operation.base_revision
            ),
            None,
        )
        self._validate_evidence(operation, previous)
        if operation.operation == "create":
            self._validate_create(operation, current)
            return

        self._validate_existing(operation, current)

    def _validate_evidence(
        self, operation: ChangeOperation, previous: AuthoringDocument | None
    ) -> None:
        document_paths = set(_flatten(operation.document.frontmatter()))
        normalized_paths = {
            path.removeprefix("x-foundry-authoring.") for path in document_paths
        }
        for evidence in operation.evidence:
            if not any(
                path == evidence.field or path.startswith(f"{evidence.field}.")
                for path in normalized_paths
            ):
                raise ChangeSetInvalid(
                    f"operation {operation.id}: evidência aponta para campo inexistente: {evidence.field}"
                )
        before = previous.frontmatter() if previous is not None else None
        changed_fields: set[str] = set()
        for change in self._field_changes(before, operation.document.frontmatter()):
            path = change.path.removeprefix("x-foundry-authoring.")
            if path.startswith("spec."):
                changed_fields.add(".".join(path.split(".")[:2]))
            elif path == "publication_state" and operation.operation == "deprecate":
                changed_fields.add(path)
        evidence_fields = {evidence.field for evidence in operation.evidence}
        uncovered = {
            field
            for field in changed_fields
            if not any(
                field == evidence
                or field.startswith(f"{evidence}.")
                or evidence.startswith(f"{field}.")
                for evidence in evidence_fields
            )
        }
        if uncovered:
            raise ChangeSetInvalid(
                f"operation {operation.id}: campos sem evidência: {', '.join(sorted(uncovered))}"
            )

    def _validate_internal_reference_dependencies(self) -> None:
        producers = {
            (*operation.document.identity, operation.document.revision): operation.id
            for operation in self.operations
        }
        for operation in self.operations:
            references = spec_references(
                operation.document.type,
                operation.document.spec,
                where=str(operation.document.relative_path),
            )
            for reference in references:
                revision = reference.revision
                if revision is None:
                    continue
                key = (
                    operation.document.tenant,
                    operation.document.area,
                    reference.type,
                    reference.id,
                    revision,
                )
                producer = producers.get(key)
                if producer is not None and producer not in operation.depends_on:
                    raise ChangeSetInvalid(
                        f"operation {operation.id}: referência interna exige dependência de {producer}"
                    )

    @staticmethod
    def _validate_create(
        operation: ChangeOperation, current: list[AuthoringDocument]
    ) -> None:
        document = operation.document
        if operation.base_revision is not None or current:
            raise ChangeSetInvalid(f"operation {operation.id}: create exige identidade nova e sem base")
        if document.publication_state != "proposed" or document.supersedes is not None:
            raise ChangeSetInvalid(f"operation {operation.id}: create deve produzir documento proposed novo")

    @staticmethod
    def _validate_existing(
        operation: ChangeOperation, current: list[AuthoringDocument]
    ) -> None:
        document = operation.document
        active = [candidate for candidate in current if candidate.publication_state == "active"]
        if len(active) != 1 or operation.base_revision != active[0].revision:
            raise ChangeSetInvalid(f"operation {operation.id}: base revision ausente ou desatualizada")
        supersedes = document.supersedes
        if supersedes is None or supersedes.revision != operation.base_revision:
            raise ChangeSetInvalid(f"operation {operation.id}: revisão deve declarar a base em supersedes")
        expected_state = "deprecated" if operation.operation == "deprecate" else "proposed"
        if document.publication_state != expected_state:
            raise ChangeSetInvalid(
                f"operation {operation.id}: {operation.operation} exige estado {expected_state}"
            )

    def _validate_dependencies(self) -> None:
        self._validate_internal_reference_dependencies()
        dependencies = {operation.id: set(operation.depends_on) for operation in self.operations}
        remaining = set(dependencies)
        while remaining:
            ready = {
                operation_id
                for operation_id in remaining
                if not dependencies[operation_id] & remaining
            }
            if not ready:
                raise ChangeSetInvalid("changeset.operations: ciclo de dependências")
            remaining -= ready

    @staticmethod
    def _field_changes(
        before: Mapping[str, Any] | None, after: Mapping[str, Any]
    ) -> tuple[FieldChange, ...]:
        old = _flatten(before or {})
        new = _flatten(after)
        changes: list[FieldChange] = []
        for path in sorted(old.keys() | new.keys()):
            if path not in old:
                changes.append(FieldChange(path, "add", after=new[path]))
            elif path not in new:
                changes.append(FieldChange(path, "remove", before=old[path]))
            elif old[path] != new[path]:
                changes.append(FieldChange(path, "replace", before=old[path], after=new[path]))
        return tuple(changes)
