"""Perfil estrito de autoria como extensão namespaced do Open Knowledge Format v0.2."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import Any

import yaml

PROFILE_KEY = "x-foundry-authoring"
PROFILE_VERSIONS = frozenset({"1"})
PUBLICATION_STATES = frozenset(
    {"draft", "proposed", "quarantined", "shadow", "active", "deprecated"}
)

_STATUS_BY_PUBLICATION_STATE = {
    "draft": "draft",
    "proposed": "draft",
    "quarantined": "draft",
    "shadow": "draft",
    "active": "stable",
    "deprecated": "deprecated",
}
_SLUG = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_VERSION = re.compile(r"^[1-9]\d*(?:\.\d+){0,2}$", re.ASCII)
_REFERENCE_TYPES = frozenset(
    {
        "copilot", "usecase", "formflow", "policy", "agent-binding", "mcp-binding",
        "middleware-binding", "adapter-binding", "bundle", "log",
    }
)
_PROFILE_KEYS = frozenset(
    {"profile_version", "id", "revision", "publication_state", "tenant", "area", "supersedes", "spec"}
)
_OKF_KEYS = frozenset({"type", "resource", "status", "generated", PROFILE_KEY})
_LEGACY_PRODUCT_KEYS = frozenset(
    {"okf_version", "version", "lifecycle", "tenant", "area", "createdBy", "provenance", "supersedes"}
)


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(child) for key, child in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(child) for child in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw(child) for child in value]
    return value


class AuthoringInvalid(ValueError):
    """O documento não satisfaz o perfil de autoria do produto."""


def _required_text(data: dict[str, Any], key: str, where: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AuthoringInvalid(f"{where}: `{key}` deve ser texto não vazio")
    return value.strip()


def _slug(value: Any, key: str, where: str) -> str:
    if not isinstance(value, str) or not _SLUG.fullmatch(value):
        raise AuthoringInvalid(
            f"{where}: `{key}` deve ter 1-63 caracteres minúsculos, números ou hífens"
        )
    return value


def _version(value: Any, key: str, where: str) -> str:
    if isinstance(value, int) and not isinstance(value, bool):
        value = str(value)
    if not isinstance(value, str) or not _VERSION.fullmatch(value):
        raise AuthoringInvalid(f"{where}: `{key}` deve ser uma versão numérica como `1` ou `1.2.0`")
    return value


def _mapping(value: Any, key: str, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AuthoringInvalid(f"{where}: `{key}` deve ser um mapa")
    return value


@dataclass(frozen=True)
class AuthoringReference:
    """Referência tenant-local a outro documento do perfil de autoria."""

    type: str
    id: str
    revision: str | None = None

    @classmethod
    def from_dict(cls, data: Any, *, where: str = "reference") -> AuthoringReference:
        if not isinstance(data, Mapping):
            raise AuthoringInvalid(f"{where}: referência deve ser um mapa")
        ref_type = _required_text(data, "type", where)
        if ref_type not in _REFERENCE_TYPES:
            raise AuthoringInvalid(f"{where}: tipo de referência desconhecido: {ref_type!r}")
        unknown = set(data) - {"type", "id", "revision"}
        if unknown:
            raise AuthoringInvalid(f"{where}: campos desconhecidos: {', '.join(sorted(unknown))}")
        revision = data.get("revision")
        return cls(
            type=ref_type,
            id=_slug(data.get("id"), "id", where),
            revision=_version(revision, "revision", where) if revision is not None else None,
        )

    def to_dict(self) -> dict[str, str]:
        out = {"type": self.type, "id": self.id}
        if self.revision is not None:
            out["revision"] = self.revision
        return out


@dataclass(frozen=True)
class AuthoringDocument:
    """Conceito OKF com o contrato do produto contido em `x-foundry-authoring`."""

    type: str
    id: str
    profile_version: str
    revision: str
    publication_state: str
    tenant: str
    area: str
    generated: Mapping[str, Any]
    body: str
    resource: str | None = None
    status: str = "draft"
    supersedes: AuthoringReference | None = None
    spec: Mapping[str, Any] = field(default_factory=dict)
    okf_metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "generated", _freeze(self.generated))
        object.__setattr__(self, "spec", _freeze(self.spec))
        object.__setattr__(self, "okf_metadata", _freeze(self.okf_metadata))

    @property
    def identity(self) -> tuple[str, str, str, str]:
        return self.tenant, self.area, self.type, self.id

    @property
    def relative_path(self) -> PurePosixPath:
        return PurePosixPath(
            "tenants", self.tenant, "areas", self.area, self.type, self.id, f"{self.revision}.md"
        )

    def frontmatter(self) -> dict[str, Any]:
        profile: dict[str, Any] = {
            "profile_version": self.profile_version,
            "id": self.id,
            "revision": self.revision,
            "publication_state": self.publication_state,
            "tenant": self.tenant,
            "area": self.area,
        }
        if self.supersedes is not None:
            profile["supersedes"] = self.supersedes.to_dict()
        profile["spec"] = _thaw(self.spec)

        header: dict[str, Any] = {"type": self.type}
        if self.resource is not None:
            header["resource"] = self.resource
        header.update({"status": self.status, "generated": _thaw(self.generated)})
        header.update(_thaw(self.okf_metadata))
        header[PROFILE_KEY] = profile
        return header


def _parse_frontmatter(text: str, *, where: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        raise AuthoringInvalid(f"{where}: frontmatter YAML ausente")
    try:
        header_text, body = text[4:].split("\n---\n", 1)
    except ValueError:
        raise AuthoringInvalid(f"{where}: frontmatter YAML não foi fechado") from None
    try:
        header = yaml.safe_load(header_text)
    except yaml.YAMLError as exc:
        raise AuthoringInvalid(f"{where}: frontmatter YAML inválido: {exc}") from exc
    if not isinstance(header, dict):
        raise AuthoringInvalid(f"{where}: frontmatter deve ser um mapa")
    return header, body


def _parse_generated(header: dict[str, Any], *, where: str) -> dict[str, Any]:
    generated = _mapping(header.get("generated"), "generated", where)
    _required_text(generated, "by", f"{where}.generated")
    _required_text(generated, "at", f"{where}.generated")
    return dict(generated)


def _parse_profile(header: dict[str, Any], *, where: str) -> dict[str, Any]:
    legacy = set(header) & _LEGACY_PRODUCT_KEYS
    if legacy:
        raise AuthoringInvalid(
            f"{where}: metadados do produto devem ficar em `{PROFILE_KEY}`: {', '.join(sorted(legacy))}"
        )
    profile = _mapping(header.get(PROFILE_KEY), PROFILE_KEY, where)
    unknown = set(profile) - _PROFILE_KEYS
    if unknown:
        raise AuthoringInvalid(f"{where}.{PROFILE_KEY}: campos desconhecidos: {', '.join(sorted(unknown))}")
    return profile


def _validate_supersedes(document: AuthoringDocument, *, where: str) -> None:
    supersedes = document.supersedes
    if supersedes is None:
        return
    if supersedes.type != document.type or supersedes.id != document.id:
        raise AuthoringInvalid(f"{where}: `supersedes` deve apontar para a mesma identidade")
    if supersedes.revision == document.revision:
        raise AuthoringInvalid(f"{where}: `supersedes` não pode apontar para a própria revisão")


def parse_authoring_document(text: str, *, where: str = "document") -> AuthoringDocument:
    """Lê um conceito OKF que optou explicitamente pelo perfil de autoria do produto."""
    header, body = _parse_frontmatter(text, where=where)
    doc_type = _required_text(header, "type", where)
    if doc_type not in _REFERENCE_TYPES:
        raise AuthoringInvalid(f"{where}: tipo autorável desconhecido: {doc_type!r}")
    profile = _parse_profile(header, where=where)
    profile_version = _required_text(profile, "profile_version", f"{where}.{PROFILE_KEY}")
    if profile_version not in PROFILE_VERSIONS:
        raise AuthoringInvalid(f"{where}: `profile_version` incompatível: {profile_version!r}")
    publication_state = _required_text(profile, "publication_state", f"{where}.{PROFILE_KEY}")
    if publication_state not in PUBLICATION_STATES:
        raise AuthoringInvalid(f"{where}: estado de publicação desconhecido: {publication_state!r}")
    status = _required_text(header, "status", where)
    expected_status = _STATUS_BY_PUBLICATION_STATE[publication_state]
    if status != expected_status:
        raise AuthoringInvalid(
            f"{where}: `status` OKF deve ser `{expected_status}` para publicação `{publication_state}`"
        )

    supersedes_data = profile.get("supersedes")
    supersedes = (
        AuthoringReference.from_dict(supersedes_data, where=f"{where}.{PROFILE_KEY}.supersedes")
        if supersedes_data is not None
        else None
    )
    if supersedes is not None and supersedes.revision is None:
        raise AuthoringInvalid(f"{where}: `supersedes` deve fixar uma revisão")
    spec = _mapping(profile.get("spec"), "spec", f"{where}.{PROFILE_KEY}")
    resource = header.get("resource")
    if resource is not None and (not isinstance(resource, str) or not resource.strip()):
        raise AuthoringInvalid(f"{where}: `resource` OKF deve ser texto não vazio quando presente")

    from .schemas import validate_spec

    validate_spec(doc_type, spec, where=f"{where}.{PROFILE_KEY}.spec")
    document = AuthoringDocument(
        type=doc_type,
        id=_slug(profile.get("id"), "id", f"{where}.{PROFILE_KEY}"),
        profile_version=profile_version,
        revision=_version(profile.get("revision"), "revision", f"{where}.{PROFILE_KEY}"),
        publication_state=publication_state,
        tenant=_slug(profile.get("tenant"), "tenant", f"{where}.{PROFILE_KEY}"),
        area=_slug(profile.get("area"), "area", f"{where}.{PROFILE_KEY}"),
        generated=_parse_generated(header, where=where),
        resource=resource.strip() if isinstance(resource, str) else None,
        status=status,
        supersedes=supersedes,
        spec=dict(spec),
        okf_metadata={key: value for key, value in header.items() if key not in _OKF_KEYS},
        body=body.strip(),
    )
    _validate_supersedes(document, where=where)
    return document


def serialize_authoring_document(document: AuthoringDocument) -> str:
    """Serializa o perfil sem perder metadados OKF que ele não governa."""
    header = yaml.safe_dump(document.frontmatter(), allow_unicode=False, sort_keys=False).rstrip()
    return f"---\n{header}\n---\n\n{document.body.strip()}\n"
