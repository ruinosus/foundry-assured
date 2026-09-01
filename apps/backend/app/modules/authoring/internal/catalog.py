"""Projeção efêmera das fontes donas para a experiência de autoria."""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from app.modules.okf.public import AuthoringInvalid


class SnapshotStale(AuthoringInvalid):
    """A continuação referencia uma fotografia que já não representa as fontes."""


class ResourceNotFound(AuthoringInvalid):
    """O identificador não existe na fonte dona."""


class SourceUnavailable(RuntimeError):
    """A fonte dona existe, mas não respondeu à observação atual."""


@dataclass(frozen=True)
class CatalogSource:
    kind: str
    owner: str
    list_items: Callable[[], Iterable[Mapping]]
    get_item: Callable[[str], Mapping]


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _canonical(value) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _snapshot(items: list[dict], gaps: list[dict], observed_at: str) -> dict:
    digest = hashlib.sha256(_canonical({"items": items, "gaps": gaps})).hexdigest()
    return {"id": f"cat_{digest[:24]}", "hash": digest, "at": observed_at}


def _encode_cursor(snapshot_hash: str, position: int) -> str:
    raw = _canonical({"hash": snapshot_hash, "position": position})
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str) -> tuple[str, int]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        value = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        snapshot_hash = value["hash"]
        position = value["position"]
        if not isinstance(snapshot_hash, str) or not isinstance(position, int) or position < 0:
            raise ValueError
        return snapshot_hash, position
    except Exception as exc:
        raise AuthoringInvalid("CATALOG_CURSOR_INVALID") from exc


def _item(source: CatalogSource, raw: Mapping) -> dict:
    resource_id = raw.get("id") or raw.get("name")
    if not isinstance(resource_id, str) or not resource_id.strip():
        raise ValueError("resource identity unavailable")
    state = str(raw.get("state") or "available")
    item = {
        "kind": source.kind,
        "id": resource_id,
        "name": raw.get("name") or resource_id,
        "state": state,
        "source": source.owner,
        "selectable": state in {"active", "available", "compatible"},
    }
    current_version = raw.get("version")
    if isinstance(current_version, Mapping):
        current_version = current_version.get("version")
    if isinstance(current_version, (str, int)) and not isinstance(current_version, bool):
        item["version"] = str(current_version)
    return item


def catalog_page(
    *,
    sources: tuple[CatalogSource, ...],
    limit: int = 50,
    cursor: str | None = None,
    kind: str | None = None,
    state: str | None = None,
    observed_at: str | None = None,
) -> dict:
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
        raise AuthoringInvalid("CATALOG_LIMIT_INVALID")

    items: list[dict] = []
    gaps: list[dict] = []
    for source in sources:
        if kind is not None and source.kind != kind:
            continue
        try:
            items.extend(_item(source, raw) for raw in source.list_items())
        except Exception:  # noqa: BLE001 - a fronteira não expõe resposta ou credencial upstream
            gaps.append(
                {
                    "kind": source.kind,
                    "source": source.owner,
                    "code": "SOURCE_UNAVAILABLE",
                }
            )

    if state is not None:
        items = [item for item in items if item["state"] == state]
    items.sort(key=lambda item: (item["kind"], item["id"]))
    gaps.sort(key=lambda gap: (gap["kind"], gap["source"]))

    snapshot = _snapshot(items, gaps, observed_at or _now())
    position = 0
    if cursor is not None:
        expected_hash, position = _decode_cursor(cursor)
        if expected_hash != snapshot["hash"]:
            raise SnapshotStale("SNAPSHOT_STALE")
        if position > len(items):
            raise AuthoringInvalid("CATALOG_CURSOR_INVALID")

    page = items[position : position + limit]
    next_position = position + len(page)
    return {
        "items": page,
        "next_cursor": (
            _encode_cursor(snapshot["hash"], next_position)
            if next_position < len(items)
            else None
        ),
        "snapshot": snapshot,
        "partial": bool(gaps),
        "gaps": gaps,
    }


def _source(kind: str, sources: tuple[CatalogSource, ...]) -> CatalogSource:
    match = next((source for source in sources if source.kind == kind), None)
    if match is None:
        raise ResourceNotFound("RESOURCE_KIND_NOT_FOUND")
    return match


def _detail(kind: str, resource_id: str, sources: tuple[CatalogSource, ...]) -> tuple[CatalogSource, dict]:
    source = _source(kind, sources)
    try:
        detail = dict(source.get_item(resource_id))
    except (KeyError, LookupError) as exc:
        raise ResourceNotFound("RESOURCE_NOT_FOUND") from exc
    except Exception as exc:
        raise SourceUnavailable("SOURCE_UNAVAILABLE") from exc
    if not detail:
        raise ResourceNotFound("RESOURCE_NOT_FOUND")
    return source, detail


def resource_detail(kind: str, resource_id: str, *, sources: tuple[CatalogSource, ...]) -> dict:
    source, detail = _detail(kind, resource_id, sources)
    observed_at = _now()
    from app.modules.tenancy.public import current_area
    from app.shared.auth import has_role

    area = current_area()
    return {
        "kind": kind,
        "id": resource_id,
        "source": source.owner,
        "definition": detail,
        "lifecycle": {
            "state": "measured",
            "value": detail.get("state") or "available",
            "source": source.owner,
            "observed_at": observed_at,
        },
        "cost": {
            "state": "unavailable",
            "value": None,
            "source": source.owner,
            "observed_at": observed_at,
            "reason": "COST_NOT_REPORTED_BY_SOURCE",
        },
        "permissions": {
            "state": "measured",
            "value": {
                "read": has_role("Reader", "Author", "Approver", "Admin"),
                "author": has_role("Author", "Admin"),
                "approve": has_role("Approver", "Admin"),
                "admin": has_role("Admin"),
            },
            "source": "Entra App Roles + active area",
            "observed_at": observed_at,
            "area_id": getattr(area, "id", None),
        },
    }


def _collection_page(
    items: list,
    *,
    source: str,
    state: str,
    coverage: str,
    limit: int,
    cursor: str | None,
) -> dict:
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
        raise AuthoringInvalid("RESOURCE_LIMIT_INVALID")
    digest = hashlib.sha256(_canonical({"items": items, "source": source})).hexdigest()
    position = 0
    if cursor is not None:
        expected_hash, position = _decode_cursor(cursor)
        if expected_hash != digest:
            raise SnapshotStale("SNAPSHOT_STALE")
        if position > len(items):
            raise AuthoringInvalid("RESOURCE_CURSOR_INVALID")
    page = items[position : position + limit]
    next_position = position + len(page)
    return {
        "items": page,
        "next_cursor": _encode_cursor(digest, next_position) if next_position < len(items) else None,
        "source": source,
        "state": state,
        "coverage": coverage,
    }


def resource_versions(
    kind: str,
    resource_id: str,
    *,
    sources: tuple[CatalogSource, ...],
    limit: int = 50,
    cursor: str | None = None,
) -> dict:
    source, detail = _detail(kind, resource_id, sources)
    versions = detail.get("versions")
    if versions is None:
        projected = [value for key in ("default", "latest") if (value := detail.get(key))]
        versions = projected or None
    return _collection_page(
        list(versions or ()),
        source=source.owner,
        state="measured" if versions is not None else "unavailable",
        coverage="official_versions" if versions is not None else "none",
        limit=limit,
        cursor=cursor,
    )



def resource_activity(
    kind: str,
    resource_id: str,
    *,
    sources: tuple[CatalogSource, ...],
    limit: int = 50,
    cursor: str | None = None,
) -> dict:
    source, detail = _detail(kind, resource_id, sources)
    if kind == "agent" and detail.get("sessions") is not None:
        items, state, coverage = list(detail["sessions"]), "measured", "recent_sessions"
    elif kind == "knowledge" and detail.get("status") is not None:
        items, state, coverage = list(detail["status"]), "measured", "source_synchronizations"
    else:
        items, state, coverage = [], "unavailable", "none"
    return _collection_page(
        items,
        source=source.owner,
        state=state,
        coverage=coverage,
        limit=limit,
        cursor=cursor,
    )
