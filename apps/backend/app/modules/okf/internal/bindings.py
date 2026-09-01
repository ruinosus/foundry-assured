"""Schemas estritos dos bindings OKF que referenciam capacidades externas."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .envelope import AuthoringInvalid, AuthoringReference

_SECRET_KEYS = frozenset({
    "apikey", "authorization", "bearertoken", "clientsecret", "connection",
    "connectionref", "credential", "credentials", "header", "headers", "password",
    "secret", "secrets", "token", "tokens",
})
_VERSION = re.compile(r"^[1-9]\d*(?:\.\d+){0,2}$", re.ASCII)
_SOURCE_ID = re.compile(r"^mep_[A-Za-z0-9._-]{1,123}$", re.ASCII)
_SNAPSHOT_ID = re.compile(r"^msnap_[A-Za-z0-9._-]{1,121}$", re.ASCII)
_SHA256 = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
_MAX_TOOLS = 200
_MAX_TOOL_NAME = 128
_AUTHORING_ROUTES = frozenset({"prompt", "workflow", "container"})
_EXTERNAL_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/@:+-]{0,511}$", re.ASCII)
_YAML_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*\.ya?ml$", re.ASCII)
_CONTAINER_REFERENCE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._/:-]*@sha256:[0-9a-f]{64}$", re.ASCII
)


@dataclass(frozen=True)
class McpBinding:
    source_kind: str
    source_name: str | None
    source_version: str | None
    use_default: bool
    source_id: str | None
    tools: tuple[str, ...]
    snapshot_id: str
    snapshot_hash: str


def _mapping(value: Any, *, where: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AuthoringInvalid(f"{where}: deve ser um mapa")
    return value


def _text(data: Mapping[str, Any], key: str, *, where: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AuthoringInvalid(f"{where}: `{key}` deve ser texto não vazio")
    return value.strip()


def _version(data: Mapping[str, Any], *, where: str) -> None:
    value = data.get("version")
    if isinstance(value, int) and not isinstance(value, bool):
        value = str(value)
    if not isinstance(value, str) or not _VERSION.fullmatch(value):
        raise AuthoringInvalid(f"{where}: `version` deve ser uma versão numérica publicada")


def _only(data: Mapping[str, Any], allowed: set[str], *, where: str) -> None:
    unknown = set(data) - allowed
    if unknown:
        raise AuthoringInvalid(f"{where}: campos desconhecidos: {', '.join(sorted(unknown))}")


def _without_secrets(value: Any, *, where: str) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
            if normalized in _SECRET_KEYS:
                raise AuthoringInvalid(f"{where}: segredo `{key}` não pode ser armazenado no perfil")
            _without_secrets(child, where=f"{where}.{key}")
    elif isinstance(value, Sequence) and not isinstance(value, str):
        for index, child in enumerate(value):
            _without_secrets(child, where=f"{where}[{index}]")


def _versioned_reference(
    value: Any,
    *,
    where: str,
    name_key: str = "name",
    extra: set[str] | None = None,
) -> None:
    data = _mapping(value, where=where)
    allowed = {name_key, "version"} | (extra or set())
    _only(data, allowed, where=where)
    _text(data, name_key, where=where)
    _version(data, where=where)


def _references(value: Any, *, where: str) -> tuple[AuthoringReference, ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, str):
        raise AuthoringInvalid(f"{where}: deve ser uma lista de referências do perfil")
    return tuple(
        AuthoringReference.from_dict(reference, where=f"{where}[{index}]")
        for index, reference in enumerate(value)
    )


def _mcp_source(
    spec: Mapping[str, Any], *, where: str
) -> tuple[str, str | None, str | None, bool, str | None]:
    origins = [key for key in ("toolbox", "endpoint") if key in spec]
    if len(origins) != 1:
        raise AuthoringInvalid(f"{where}: informe exatamente um de `toolbox` ou `endpoint`")

    if "toolbox" in spec:
        toolbox = _mapping(spec["toolbox"], where=f"{where}.toolbox")
        _only(toolbox, {"name", "version", "useDefault"}, where=f"{where}.toolbox")
        source_name = _text(toolbox, "name", where=f"{where}.toolbox")
        selectors = [key for key in ("version", "useDefault") if key in toolbox]
        if len(selectors) != 1:
            raise AuthoringInvalid(
                f"{where}.toolbox: informe exatamente um de `version` ou `useDefault`"
            )
        if "version" in toolbox:
            _version(toolbox, where=f"{where}.toolbox")
            return "toolbox", source_name, str(toolbox["version"]), False, None
        elif toolbox["useDefault"] is not True:
            raise AuthoringInvalid(f"{where}.toolbox: `useDefault` deve ser true")
        return "toolbox", source_name, None, True, None

    endpoint = _mapping(spec["endpoint"], where=f"{where}.endpoint")
    _only(endpoint, {"id"}, where=f"{where}.endpoint")
    source_id = _text(endpoint, "id", where=f"{where}.endpoint")
    if not _SOURCE_ID.fullmatch(source_id):
        raise AuthoringInvalid(f"{where}.endpoint: `id` inválido")
    return "endpoint", None, None, False, source_id


def _mcp_tools(value: Any, *, where: str) -> tuple[str, ...]:
    raw_tools = value
    if not isinstance(raw_tools, Sequence) or isinstance(raw_tools, str) or not raw_tools:
        raise AuthoringInvalid(f"{where}: deve ser uma lista não vazia")
    if len(raw_tools) > _MAX_TOOLS:
        raise AuthoringInvalid(f"{where}: excede o limite de {_MAX_TOOLS} tools")
    tools = tuple(
        _text({"name": item}, "name", where=f"{where}[{index}]")
        for index, item in enumerate(raw_tools)
    )
    if any(len(name) > _MAX_TOOL_NAME for name in tools):
        raise AuthoringInvalid(f"{where}: nome de tool excede {_MAX_TOOL_NAME} caracteres")
    if len(set(tools)) != len(tools):
        raise AuthoringInvalid(f"{where}: nomes de tool devem ser únicos")
    return tools


def _reviewed_snapshot(value: Any, *, where: str) -> tuple[str, str]:
    reviewed = _mapping(value, where=where)
    _only(reviewed, {"id", "hash"}, where=where)
    snapshot_id = _text(reviewed, "id", where=where)
    snapshot_hash = _text(reviewed, "hash", where=where)
    if not _SNAPSHOT_ID.fullmatch(snapshot_id):
        raise AuthoringInvalid(f"{where}: `id` inválido")
    if not _SHA256.fullmatch(snapshot_hash):
        raise AuthoringInvalid(f"{where}: `hash` deve ser SHA-256 hexadecimal")
    return snapshot_id, snapshot_hash


def parse_mcp_binding(spec: Mapping[str, Any], *, where: str = "mcp-binding.spec") -> McpBinding:
    """Valida e projeta somente referências inertes de um binding MCP."""
    _without_secrets(spec, where=where)
    _only(spec, {"toolbox", "endpoint", "tools", "reviewedSnapshot"}, where=where)
    source_kind, source_name, source_version, use_default, source_id = _mcp_source(
        spec, where=where
    )
    tools = _mcp_tools(spec.get("tools"), where=f"{where}.tools")
    snapshot_id, snapshot_hash = _reviewed_snapshot(
        spec.get("reviewedSnapshot"), where=f"{where}.reviewedSnapshot"
    )

    return McpBinding(
        source_kind=source_kind,
        source_name=source_name,
        source_version=source_version,
        use_default=use_default,
        source_id=source_id,
        tools=tools,
        snapshot_id=snapshot_id,
        snapshot_hash=snapshot_hash,
    )


def binding_references(doc_type: str, spec: dict[str, Any], *, where: str) -> tuple[AuthoringReference, ...]:
    if doc_type not in {"agent-binding", "middleware-binding"}:
        return ()
    return _references(spec.get("requires"), where=f"{where}.requires")


def validate_binding(doc_type: str, spec: dict[str, Any], *, where: str) -> None:
    """Valida o payload específico dos bindings implementados na primeira vertical."""
    _without_secrets(spec, where=where)

    if doc_type == "agent-binding":
        _only(spec, {"agent", "authoringRoute", "requires"}, where=where)
        _versioned_reference(spec.get("agent"), where=f"{where}.agent")
        route = spec.get("authoringRoute")
        if route is not None and route not in _AUTHORING_ROUTES:
            raise AuthoringInvalid(
                f"{where}.authoringRoute: use `prompt`, `workflow` ou `container`"
            )
        binding_references(doc_type, spec, where=where)
        return

    if doc_type == "mcp-binding":
        parse_mcp_binding(spec, where=where)
        return

    if doc_type == "middleware-binding":
        _only(spec, {"implementation", "configuration", "requires"}, where=where)
        _versioned_reference(
            spec.get("implementation"),
            where=f"{where}.implementation",
            extra={"runtime"},
        )
        implementation = _mapping(spec["implementation"], where=f"{where}.implementation")
        _text(implementation, "runtime", where=f"{where}.implementation")
        binding_references(doc_type, spec, where=where)
        if "configuration" in spec:
            _mapping(spec["configuration"], where=f"{where}.configuration")


def validate_binding_resource(
    doc_type: str,
    spec: Mapping[str, Any],
    resource: str | None,
    *,
    where: str,
) -> None:
    if doc_type != "agent-binding" or "authoringRoute" not in spec:
        return
    if resource is None:
        return
    route = str(spec["authoringRoute"])
    prefix = f"{route}:"
    reference = resource[len(prefix):] if resource and resource.startswith(prefix) else ""
    valid_format = (
        _CONTAINER_REFERENCE.fullmatch(reference)
        if route == "container"
        else _YAML_REFERENCE.fullmatch(reference)
    )
    if (
        not reference
        or not _EXTERNAL_REFERENCE.fullmatch(reference)
        or not valid_format
        or ".." in reference
    ):
        raise AuthoringInvalid(
            f"{where}: deve usar `{prefix}` seguido de uma referência externa segura"
        )
