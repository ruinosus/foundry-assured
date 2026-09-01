"""Permissões declarativas de autoria dos documentos `type: copilot`."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .envelope import AuthoringDocument, AuthoringInvalid

OPERATIONS = frozenset({"create", "revise", "deprecate"})
_TYPE = re.compile(r"^[a-z][a-z0-9-]*$", re.ASCII)
_ADMIN_ONLY = frozenset({"policy", "connection", "middleware-implementation", "tenant-config"})


def _operation_set(raw: Mapping[str, Any], *, where: str) -> frozenset[str]:
    raw_operations = raw.get("operations")
    if not isinstance(raw_operations, Sequence) or isinstance(raw_operations, str) or not raw_operations:
        raise AuthoringInvalid(f"{where}: `operations` deve ser uma lista não vazia")
    if any(not isinstance(operation, str) or operation not in OPERATIONS for operation in raw_operations):
        raise AuthoringInvalid(f"{where}: operação desconhecida")
    operation_set = frozenset(raw_operations)
    if len(operation_set) != len(raw_operations):
        raise AuthoringInvalid(f"{where}: operação duplicada")
    return operation_set


def _rule(raw: Any, *, where: str, operations: bool) -> tuple[str, frozenset[str]]:
    if not isinstance(raw, Mapping):
        raise AuthoringInvalid(f"{where}: deve ser um mapa")
    allowed = {"type", "operations"} if operations else {"type"}
    unknown = set(raw) - allowed
    if unknown:
        raise AuthoringInvalid(f"{where}: campos desconhecidos: {', '.join(sorted(unknown))}")
    target_type = raw.get("type")
    if not isinstance(target_type, str) or not _TYPE.fullmatch(target_type):
        raise AuthoringInvalid(f"{where}: `type` inválido")
    return target_type, _operation_set(raw, where=where) if operations else frozenset()


def _rules(value: Any, *, key: str, operations: bool) -> tuple[tuple[str, frozenset[str]], ...]:
    if not isinstance(value, Sequence) or isinstance(value, str):
        raise AuthoringInvalid(f"copilot.spec.{key}: deve ser uma lista")
    parsed: list[tuple[str, frozenset[str]]] = []
    seen: set[str] = set()
    for index, raw in enumerate(value):
        where = f"copilot.spec.{key}[{index}]"
        target_type, operation_set = _rule(raw, where=where, operations=operations)
        if target_type in seen:
            raise AuthoringInvalid(f"{where}: regra duplicada para `{target_type}`")
        seen.add(target_type)
        parsed.append((target_type, operation_set))
    return tuple(parsed)


@dataclass(frozen=True)
class CopilotPermissions:
    grants: dict[str, frozenset[str]]
    denied: frozenset[str]

    @classmethod
    def from_spec(cls, spec: Mapping[str, Any]) -> CopilotPermissions:
        unknown = set(spec) - {"writes", "cannotWrite"}
        if unknown:
            raise AuthoringInvalid(f"copilot.spec: campos desconhecidos: {', '.join(sorted(unknown))}")
        grants = dict(_rules(spec.get("writes"), key="writes", operations=True))
        denied = frozenset(target_type for target_type, _ in _rules(
            spec.get("cannotWrite"), key="cannotWrite", operations=False
        ))
        return cls(grants=grants, denied=denied)

    def allows(self, target_type: str, operation: str) -> bool:
        if target_type in self.denied or target_type in _ADMIN_ONLY:
            return False
        return operation in OPERATIONS and operation in self.grants.get(target_type, frozenset())


def validate_copilot(spec: Mapping[str, Any]) -> None:
    CopilotPermissions.from_spec(spec)


def copilot_allows(document: AuthoringDocument, target_type: str, operation: str) -> bool:
    if document.type != "copilot":
        raise AuthoringInvalid("authoring: permissões só existem em documento `type: copilot`")
    return CopilotPermissions.from_spec(document.spec).allows(target_type, operation)
