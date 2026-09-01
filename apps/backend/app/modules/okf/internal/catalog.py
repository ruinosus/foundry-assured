"""Catálogo imutável do perfil de autoria, sem substituir catálogos operacionais."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from .envelope import (
    AuthoringDocument,
    AuthoringInvalid,
    AuthoringReference,
    parse_authoring_document,
    serialize_authoring_document,
)
from .schemas import spec_references

_FLOATING_STATES = frozenset({"draft", "proposed"})


@dataclass(frozen=True, slots=True, init=False)
class AuthoringCatalog:
    """Conjunto validado de revisões do perfil, isolado pela identidade de origem."""

    _documents: Mapping[tuple[str, str, str, str, str], AuthoringDocument]

    def __init__(self, documents: Iterable[AuthoringDocument]) -> None:
        indexed: dict[tuple[str, str, str, str, str], AuthoringDocument] = {}
        active: set[tuple[str, str, str, str]] = set()
        for candidate in documents:
            document = parse_authoring_document(
                serialize_authoring_document(candidate),
                where=f"catalog:{candidate.relative_path}",
            )
            key = (*document.identity, document.revision)
            if key in indexed:
                raise AuthoringInvalid(f"catalog: revisão já existe e não pode ser sobrescrita: {document.relative_path}")
            if document.publication_state == "active" and document.identity in active:
                raise AuthoringInvalid(f"catalog: mais de uma revisão ativa para {document.identity!r}")
            indexed[key] = document
            if document.publication_state == "active":
                active.add(document.identity)

        object.__setattr__(self, "_documents", MappingProxyType(indexed))
        for document in self._documents.values():
            self.resolved_references(document)

    def resolve(self, source: AuthoringDocument, reference: AuthoringReference) -> AuthoringDocument:
        identity = (source.tenant, source.area, reference.type, reference.id)
        if reference.revision is not None:
            target = self._documents.get((*identity, reference.revision))
            if target is None:
                raise AuthoringInvalid(f"{source.relative_path}: referência inexistente: {reference.to_dict()!r}")
            return target

        if source.publication_state not in _FLOATING_STATES:
            raise AuthoringInvalid(f"{source.relative_path}: referência flutuante não é permitida em `{source.publication_state}`")
        candidates = [
            document
            for key, document in self._documents.items()
            if key[:4] == identity and document.publication_state == "active"
        ]
        if len(candidates) != 1:
            raise AuthoringInvalid(
                f"{source.relative_path}: referência flutuante exige exatamente uma revisão ativa; encontradas {len(candidates)}"
            )
        return candidates[0]

    def resolved_references(self, document: AuthoringDocument) -> tuple[AuthoringDocument, ...]:
        references: list[AuthoringReference] = []
        if document.supersedes is not None:
            references.append(document.supersedes)
        references.extend(spec_references(document.type, document.spec, where=str(document.relative_path)))
        return tuple(self.resolve(document, reference) for reference in references)
