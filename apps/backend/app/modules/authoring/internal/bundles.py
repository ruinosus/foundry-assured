"""Projeção de bundles sobre revisões imutáveis de ChangeSet."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.modules.okf.public import (
    AuthoringInvalid,
    parse_authoring_document,
    spec_references,
)

from .catalog import ResourceNotFound, SourceUnavailable, resource_detail

if TYPE_CHECKING:
    from .catalog import CatalogSource
    from .changesets import ChangeSetScope, ChangeSetService, StoredChangeSet


class BundleNotFound(AuthoringInvalid):
    """O ChangeSet não contém um documento bundle no escopo resolvido."""


class BundleBlocked(AuthoringInvalid):
    """A revisão possui lacunas bloqueadoras ou referências não resolvidas."""


@dataclass(frozen=True, slots=True)
class BundleService:
    changesets: ChangeSetService
    sources: tuple[CatalogSource, ...]

    @staticmethod
    def _documents(record: StoredChangeSet) -> list[dict[str, Any]]:
        documents: list[dict[str, Any]] = []
        for operation in record.content["operations"]:
            raw = operation.get("document")
            if raw is None:
                continue
            document = parse_authoring_document(raw, where=f"changeset:{record.id}")
            documents.append(
                {
                    "key": f"{document.type}:{document.id}@{document.revision}",
                    "type": document.type,
                    "id": document.id,
                    "revision": document.revision,
                    "operation": operation["operation"],
                    "text": raw,
                    "spec": dict(document.spec),
                    "references": [
                        {
                            "type": reference.type,
                            "id": reference.id,
                            "revision": reference.revision,
                        }
                        for reference in spec_references(
                            document.type,
                            dict(document.spec),
                            where=f"{document.type}:{document.id}",
                        )
                    ],
                }
            )
        return documents

    def _reference_status(
        self,
        reference: dict[str, str],
        internal: set[tuple[str, str, str]],
    ) -> tuple[str, str]:
        key = (reference["type"], reference["id"], reference["revision"])
        if key in internal:
            return "approved", "changeset"
        try:
            detail = resource_detail(
                reference["type"], reference["id"], sources=self.sources
            )
            status = (
                "approved"
                if str(detail.get("version")) == reference["revision"]
                else "failed"
            )
            return status, "catalog"
        except ResourceNotFound:
            return "failed", "catalog"
        except SourceUnavailable:
            return "pending", "catalog"

    def _references(
        self, documents: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
        internal = {
            (document["type"], document["id"], document["revision"])
            for document in documents
        }
        dependencies: list[dict[str, Any]] = []
        checks: list[dict[str, str]] = []
        for document in documents:
            for reference in document["references"]:
                status, source = self._reference_status(reference, internal)
                target = (
                    f"{reference['type']}:{reference['id']}@{reference['revision']}"
                )
                dependencies.append(
                    {
                        "from": document["key"],
                        "to": target,
                        "source": source,
                        "status": status,
                    }
                )
                checks.append(
                    {
                        "id": f"reference:{document['key']}->{target}",
                        "status": status,
                        "reason": f"Referência resolvida em {source}."
                        if status == "approved"
                        else "Referência não confirmada na revisão ou no catálogo factual.",
                    }
                )
        return dependencies, checks

    def _project(self, record: StoredChangeSet) -> dict[str, Any]:
        documents = self._documents(record)
        roots = [document for document in documents if document["type"] == "bundle"]
        if not roots:
            raise BundleNotFound("BUNDLE_NOT_FOUND")
        dependencies, checks = self._references(documents)
        gaps = record.content.get("gaps", [])
        if gaps:
            checks.append(
                {
                    "id": "blocking-gaps",
                    "status": "failed",
                    "reason": f"A revisão possui {len(gaps)} lacuna(s) declarada(s).",
                }
            )
        checks.insert(
            0,
            {
                "id": "schema",
                "status": "approved",
                "reason": f"{len(documents)} documento(s) OKF válido(s).",
            },
        )
        return {
            **record.to_dict(),
            "bundle": roots[0],
            "documents": documents,
            "dependencies": dependencies,
            "validations": checks,
            "canSubmit": record.state == "draft"
            and all(check["status"] == "approved" for check in checks),
        }

    def list(self, scope: ChangeSetScope) -> list[dict[str, Any]]:
        bundles: list[dict[str, Any]] = []
        for record in self.changesets.list(scope):
            try:
                bundles.append(self._project(record))
            except BundleNotFound:
                continue
        return bundles

    def get(
        self, scope: ChangeSetScope, changeset_id: str, *, revision: int | None = None
    ) -> dict[str, Any]:
        record = (
            self.changesets.get_revision(scope, changeset_id, revision)
            if revision is not None
            else self.changesets.get(scope, changeset_id)
        )
        return self._project(record)

    def submit(
        self, scope: ChangeSetScope, changeset_id: str, *, expected_etag: str
    ) -> dict[str, Any]:
        projection = self.get(scope, changeset_id)
        if not projection["canSubmit"]:
            raise BundleBlocked("BUNDLE_SUBMISSION_BLOCKED")
        return self._project(
            self.changesets.submit(scope, changeset_id, expected_etag=expected_etag)
        )

    def update(
        self,
        scope: ChangeSetScope,
        changeset_id: str,
        *,
        expected_etag: str,
        content: dict[str, Any],
        base_snapshot_id: str | None = None,
    ) -> dict[str, Any]:
        return self._project(
            self.changesets.update(
                scope,
                changeset_id,
                expected_etag=expected_etag,
                content=content,
                base_snapshot_id=base_snapshot_id,
            )
        )

    def revise(
        self, scope: ChangeSetScope, changeset_id: str, *, expected_etag: str
    ) -> dict[str, Any]:
        return self._project(
            self.changesets.revise(scope, changeset_id, expected_etag=expected_etag)
        )
