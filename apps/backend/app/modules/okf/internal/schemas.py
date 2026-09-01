"""Schemas por tipo do perfil de autoria Foundry sobre conceitos OKF."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .authoring import validate_copilot
from .bindings import binding_references, validate_binding
from .envelope import AuthoringInvalid, AuthoringReference

_BINDINGS = frozenset({"agent-binding", "mcp-binding", "middleware-binding"})
_FIELD_TYPES = frozenset({"choice", "files", "longtext", "multi", "pair", "secret", "text"})


def _only(spec: dict[str, Any], allowed: set[str], *, where: str) -> None:
    unknown = set(spec) - allowed
    if unknown:
        raise AuthoringInvalid(f"{where}: campos desconhecidos: {', '.join(sorted(unknown))}")


def _text(value: Any, *, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AuthoringInvalid(f"{where}: deve ser texto não vazio")
    return value.strip()


def _mapping(value: Any, *, where: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AuthoringInvalid(f"{where}: deve ser um mapa")
    return value


def _list(value: Any, *, where: str, empty: bool = False) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, str) or (not empty and not value):
        raise AuthoringInvalid(f"{where}: deve ser uma lista{' não vazia' if not empty else ''}")
    return value


def _references(value: Any, *, where: str, empty: bool = False) -> tuple[AuthoringReference, ...]:
    return tuple(
        AuthoringReference.from_dict(item, where=f"{where}[{index}]")
        for index, item in enumerate(_list(value, where=where, empty=empty))
    )


def _validate_usecase(spec: dict[str, Any], *, where: str) -> None:
    _only(spec, {"requires", "targets", "approval", "cost", "citation", "gaps"}, where=where)
    _references(spec.get("requires"), where=f"{where}.requires")
    _references(spec.get("targets"), where=f"{where}.targets")
    approval = _mapping(spec.get("approval"), where=f"{where}.approval")
    _only(approval, {"required", "role"}, where=f"{where}.approval")
    if approval.get("required") is not True or approval.get("role") not in {"Admin", "Approver"}:
        raise AuthoringInvalid(f"{where}.approval: exige `required: true` e papel Admin ou Approver")
    cost = _mapping(spec.get("cost"), where=f"{where}.cost")
    _only(cost, {"kind", "estimate", "currency"}, where=f"{where}.cost")
    if cost.get("kind") not in {"known", "unknown"}:
        raise AuthoringInvalid(f"{where}.cost: `kind` deve ser known ou unknown")
    if cost["kind"] == "known" and (
        not isinstance(cost.get("estimate"), (int, float)) or isinstance(cost.get("estimate"), bool)
    ):
        raise AuthoringInvalid(f"{where}.cost: custo known exige `estimate` numérico")
    if cost["kind"] == "known":
        _text(cost.get("currency"), where=f"{where}.cost.currency")
    elif set(cost) != {"kind"}:
        raise AuthoringInvalid(f"{where}.cost: custo unknown não aceita estimate ou currency")
    if spec.get("citation") not in {"required", "optional", "none"}:
        raise AuthoringInvalid(f"{where}.citation: valor desconhecido")
    for index, gap in enumerate(_list(spec.get("gaps"), where=f"{where}.gaps", empty=True)):
        item = _mapping(gap, where=f"{where}.gaps[{index}]")
        _only(item, {"capability", "reason", "status"}, where=f"{where}.gaps[{index}]")
        _text(item.get("capability"), where=f"{where}.gaps[{index}].capability")
        _text(item.get("reason"), where=f"{where}.gaps[{index}].reason")
        if item.get("status") not in {"missing", "requires_configuration", "shadow"}:
            raise AuthoringInvalid(f"{where}.gaps[{index}]: status desconhecido")


def _validate_formflow(spec: dict[str, Any], *, where: str) -> None:
    _only(spec, {"sections", "review", "plan"}, where=where)
    for index, section in enumerate(_list(spec.get("sections"), where=f"{where}.sections")):
        section_where = f"{where}.sections[{index}]"
        item = _mapping(section, where=section_where)
        _only(
            item,
            {"id", "title", "help", "optional", "lockedUntil", "lockedHelp", "fields"},
            where=section_where,
        )
        _text(item.get("id"), where=f"{section_where}.id")
        for key in ("title", "help", "lockedUntil", "lockedHelp"):
            if key in item:
                _text(item[key], where=f"{section_where}.{key}")
        if "optional" in item and not isinstance(item["optional"], bool):
            raise AuthoringInvalid(f"{section_where}.optional: deve ser booleano")
        for field_index, field in enumerate(
            _list(item.get("fields"), where=f"{section_where}.fields")
        ):
            _validate_formflow_field(field, where=f"{section_where}.fields[{field_index}]")

    for index, review in enumerate(
        _list(spec.get("review"), where=f"{where}.review", empty=True)
    ):
        _validate_formflow_review(review, where=f"{where}.review[{index}]")
    for index, plan in enumerate(_list(spec.get("plan"), where=f"{where}.plan", empty=True)):
        _validate_formflow_plan(plan, where=f"{where}.plan[{index}]")


def _validate_formflow_field(value: Any, *, where: str) -> None:
    field = _mapping(value, where=where)
    _only(
        field,
        {
            "id", "label", "type", "required", "ai", "placeholder", "help", "rules",
            "rows", "initial", "catalog", "emptyHelp", "options", "parts", "retain",
            "visibleWhen",
        },
        where=where,
    )
    _text(field.get("id"), where=f"{where}.id")
    if field.get("type") not in _FIELD_TYPES:
        raise AuthoringInvalid(f"{where}.type: tipo de campo desconhecido")
    if "visibleWhen" in field:
        condition = _mapping(field["visibleWhen"], where=f"{where}.visibleWhen")
        _only(condition, {"field", "equals"}, where=f"{where}.visibleWhen")
        _text(condition.get("field"), where=f"{where}.visibleWhen.field")
        _text(condition.get("equals"), where=f"{where}.visibleWhen.equals")
    _validate_optional_texts(field, ("label", "placeholder", "help", "emptyHelp"), where=where)
    _validate_optional_booleans(field, ("required", "ai", "retain"), where=where)
    if "rows" in field and (
        not isinstance(field["rows"], int) or isinstance(field["rows"], bool) or field["rows"] < 1
    ):
        raise AuthoringInvalid(f"{where}.rows: deve ser inteiro positivo")
    for key in ("rules", "options"):
        if key in field:
            _validate_text_list(field[key], where=f"{where}.{key}")
    if "catalog" in field:
        _validate_formflow_catalog(field["catalog"], where=f"{where}.catalog")
    if "parts" in field:
        _validate_formflow_parts(field["parts"], where=f"{where}.parts")


def _validate_optional_texts(
    data: Mapping[str, Any], keys: tuple[str, ...], *, where: str
) -> None:
    for key in keys:
        if key in data:
            _text(data[key], where=f"{where}.{key}")


def _validate_optional_booleans(
    data: Mapping[str, Any], keys: tuple[str, ...], *, where: str
) -> None:
    for key in keys:
        if key in data and not isinstance(data[key], bool):
            raise AuthoringInvalid(f"{where}.{key}: deve ser booleano")


def _validate_text_list(value: Any, *, where: str) -> None:
    for index, item in enumerate(_list(value, where=where)):
        _text(item, where=f"{where}[{index}]")


def _validate_formflow_catalog(value: Any, *, where: str) -> None:
    catalog = _mapping(value, where=where)
    _only(catalog, {"source", "key"}, where=where)
    _text(catalog.get("source"), where=f"{where}.source")
    _text(catalog.get("key"), where=f"{where}.key")


def _validate_formflow_parts(value: Any, *, where: str) -> None:
    for index, raw_part in enumerate(_list(value, where=where)):
        part_where = f"{where}[{index}]"
        part = _mapping(raw_part, where=part_where)
        _only(part, {"id", "placeholder"}, where=part_where)
        _text(part.get("id"), where=f"{part_where}.id")
        _validate_optional_texts(part, ("placeholder",), where=part_where)


def _validate_formflow_review(value: Any, *, where: str) -> None:
    review = _mapping(value, where=where)
    _only(
        review,
        {"label", "from", "variant", "fromCapabilities", "fields", "const", "fromFiles"},
        where=where,
    )
    _text(review.get("label"), where=f"{where}.label")
    for key in ("from", "const"):
        if key in review:
            _text(review[key], where=f"{where}.{key}")
    for key in ("fromCapabilities", "fromFiles"):
        if key in review and not isinstance(review[key], bool):
            raise AuthoringInvalid(f"{where}.{key}: deve ser booleano")
    if "fields" in review:
        for index, field in enumerate(_list(review["fields"], where=f"{where}.fields")):
            _text(field, where=f"{where}.fields[{index}]")
    if "variant" in review:
        variant = _mapping(review["variant"], where=f"{where}.variant")
        _only(variant, {"when", "then"}, where=f"{where}.variant")
        _text(variant.get("when"), where=f"{where}.variant.when")
        _text(variant.get("then"), where=f"{where}.variant.then")


def _validate_formflow_plan(value: Any, *, where: str) -> None:
    plan = _mapping(value, where=where)
    _only(
        plan,
        {"id", "title", "method", "path", "approval", "note", "encoding", "requires", "onFailure"},
        where=where,
    )
    for key in ("id", "title"):
        _text(plan.get(key), where=f"{where}.{key}")
    for key in ("path", "note", "encoding", "onFailure"):
        if key in plan:
            _text(plan[key], where=f"{where}.{key}")
    if "method" in plan and plan["method"] not in {"DELETE", "PATCH", "POST", "PUT"}:
        raise AuthoringInvalid(f"{where}.method: método de escrita desconhecido")
    if "requires" in plan:
        for index, requirement in enumerate(_list(plan["requires"], where=f"{where}.requires")):
            _text(requirement, where=f"{where}.requires[{index}]")
    if "approval" in plan:
        approval = _mapping(plan["approval"], where=f"{where}.approval")
        _only(approval, {"required", "role", "because"}, where=f"{where}.approval")
        if approval.get("required") is not True or approval.get("role") not in {"Admin", "Approver"}:
            raise AuthoringInvalid(f"{where}.approval: exige `required: true` e papel conhecido")
        if "because" in approval:
            _text(approval["because"], where=f"{where}.approval.because")


def _validate_policy(spec: dict[str, Any], *, where: str) -> None:
    _only(spec, {"enforcement", "sources"}, where=where)
    if spec.get("enforcement") != "external":
        raise AuthoringInvalid(f"{where}: policy deve declarar `enforcement: external`")
    for index, source in enumerate(_list(spec.get("sources"), where=f"{where}.sources")):
        _text(source, where=f"{where}.sources[{index}]")


def _validate_adapter(spec: dict[str, Any], *, where: str) -> None:
    _only(spec, {"adapter", "connection", "requires"}, where=where)
    adapter = _mapping(spec.get("adapter"), where=f"{where}.adapter")
    _only(adapter, {"name", "version", "runtime"}, where=f"{where}.adapter")
    for key in ("name", "version", "runtime"):
        _text(adapter.get(key), where=f"{where}.adapter.{key}")
    _text(spec.get("connection"), where=f"{where}.connection")
    _references(spec.get("requires", []), where=f"{where}.requires", empty=True)


def _validate_bundle(spec: dict[str, Any], *, where: str) -> None:
    _only(spec, {"includes"}, where=where)
    _references(spec.get("includes"), where=f"{where}.includes")


def _validate_log(spec: dict[str, Any], *, where: str) -> None:
    _only(spec, {"events"}, where=where)
    for index, event in enumerate(_list(spec.get("events"), where=f"{where}.events", empty=True)):
        item = _mapping(event, where=f"{where}.events[{index}]")
        _only(item, {"at", "by", "action", "revision"}, where=f"{where}.events[{index}]")
        for key in ("at", "by", "action", "revision"):
            _text(item.get(key), where=f"{where}.events[{index}].{key}")


def validate_spec(doc_type: str, spec: dict[str, Any], *, where: str) -> None:
    """Despacha todo tipo autorável para exatamente um schema conhecido."""
    if doc_type == "copilot":
        validate_copilot(spec)
    elif doc_type in _BINDINGS:
        validate_binding(doc_type, spec, where=where)
    elif doc_type == "adapter-binding":
        _validate_adapter(spec, where=where)
    elif doc_type == "usecase":
        _validate_usecase(spec, where=where)
    elif doc_type == "formflow":
        _validate_formflow(spec, where=where)
    elif doc_type == "policy":
        _validate_policy(spec, where=where)
    elif doc_type == "bundle":
        _validate_bundle(spec, where=where)
    elif doc_type == "log":
        _validate_log(spec, where=where)
    else:
        raise AuthoringInvalid(f"{where}: schema ausente para `{doc_type}`")


def spec_references(doc_type: str, spec: dict[str, Any], *, where: str) -> tuple[AuthoringReference, ...]:
    if doc_type in {"agent-binding", "middleware-binding"}:
        return binding_references(doc_type, spec, where=where)
    if doc_type == "adapter-binding":
        return _references(spec.get("requires", []), where=f"{where}.requires", empty=True)
    if doc_type == "usecase":
        return (*_references(spec["requires"], where=f"{where}.requires"),
                *_references(spec["targets"], where=f"{where}.targets"))
    if doc_type == "bundle":
        return _references(spec["includes"], where=f"{where}.includes")
    return ()
