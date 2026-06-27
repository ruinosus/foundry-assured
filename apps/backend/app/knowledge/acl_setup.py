"""Phase 4 — document-level ACL on the Cockpit KB index (reproducible setup).

Makes the manual spike reproducible: adds a `groups` permission-filter field to the
KB index, classifies every document by sensitivity tier, stamps its allowed Entra
group, and enables query-time trimming. After this, the agentic retrieve only returns
documents the *caller* is entitled to (the SecureAzureAISearchProvider passes the
caller's identity as x-ms-query-source-authorization).

Proven on the live index: same query, User A (all tiers) saw internal+confidential+public,
User B (public only) saw public-only, no token saw nothing.

The `groups` field is immutable once created and a permission-filter field forces the
option on, so re-stamping toggles permissionFilterOption disabled→populate→enabled
(documents with no group are invisible to everyone while enabled, so we must populate
under the disabled window).

Run from apps/backend after groups exist (infra/entra) and their IDs are in .env:
    uv run python -m app.knowledge.acl_setup
"""

from __future__ import annotations

import json
import urllib.request

from azure.identity import DefaultAzureCredential

from app.core.settings import settings

_API = "2025-08-01-preview"
_INDEX = "cockpit-docbundles-ks-index"
_SEARCH_SCOPE = "https://search.azure.com/.default"

# Classification tiers → Entra group object-IDs (from infra/entra, via env). A tenant
# adapts the mapping below to its own data classification without touching identities.
_CONFIDENTIAL_MARKERS = ("ARCHITECTURE", "OBSERVABILITY", "SUPERVISOR", "SECURITY", "VALIDACAO", "ANALISE_COMPLETA")
_PUBLIC_MARKERS = ("README", "OVERVIEW", "FAQ", "MODUS")


def _tier_group(blob_url: str) -> str:
    """Map a document (by its blob name) to the group allowed to read it."""
    name = (blob_url or "").rsplit("/", 1)[-1].upper()
    if any(k in name for k in _CONFIDENTIAL_MARKERS):
        return settings.cockpit_acl_confidential_group
    if any(k in name for k in _PUBLIC_MARKERS):
        return settings.cockpit_acl_public_group
    return settings.cockpit_acl_internal_group


def _req(token: str, method: str, path: str, body: dict | None = None) -> dict | None:
    url = f"{settings.azure_search_endpoint}/{path}"
    req = urllib.request.Request(
        url, method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    data = json.dumps(body).encode() if body is not None else None
    resp = urllib.request.urlopen(req, data, timeout=90)
    try:
        return json.load(resp)
    except Exception:  # noqa: BLE001 — 204 No Content on index PUT
        return None


def _set_option(token: str, index: dict, state: str) -> None:
    index = {k: v for k, v in index.items() if not k.startswith("@odata")}
    index["permissionFilterOption"] = state  # "enabled" | "disabled"
    _req(token, "PUT", f"indexes/{_INDEX}?api-version={_API}", index)


def setup_acl() -> None:
    if not (settings.cockpit_acl_public_group and settings.cockpit_acl_internal_group
            and settings.cockpit_acl_confidential_group):
        raise SystemExit("Set COCKPIT_ACL_{PUBLIC,INTERNAL,CONFIDENTIAL}_GROUP first (infra/entra).")

    token = DefaultAzureCredential().get_token(_SEARCH_SCOPE).token
    index = _req(token, "GET", f"indexes/{_INDEX}?api-version={_API}")
    assert index is not None

    field_names = {f["name"] for f in index["fields"]}
    if "groups" not in field_names:
        index["fields"].append({
            "name": "groups", "type": "Collection(Edm.String)",
            "filterable": True, "retrievable": True, "searchable": False,
            "permissionFilter": "groupIds",
        })
        _set_option(token, index, "enabled")  # create the field
        index = _req(token, "GET", f"indexes/{_INDEX}?api-version={_API}")
        assert index is not None
        print("✓ permission field 'groups' added")

    # Populate under a disabled window (documents with no group are invisible when on).
    _set_option(token, index, "disabled")
    docs, skip = [], 0
    while True:
        page = _req(token, "GET", f"indexes/{_INDEX}/docs?api-version={_API}&search=*&$select=uid,blob_url&$top=1000&$skip={skip}")
        rows = (page or {}).get("value", [])
        if not rows:
            break
        docs += rows
        skip += len(rows)
        if len(rows) < 1000:
            break

    from collections import Counter
    tally: Counter[str] = Counter()
    label = {settings.cockpit_acl_public_group: "public", settings.cockpit_acl_internal_group: "internal",
             settings.cockpit_acl_confidential_group: "confidential"}
    batch: list[dict] = []
    for d in docs:
        g = _tier_group(d.get("blob_url", ""))
        tally[label.get(g, g)] += 1
        batch.append({"@search.action": "mergeOrUpload", "uid": d["uid"], "groups": [g]})
        if len(batch) >= 500:
            _req(token, "POST", f"indexes/{_INDEX}/docs/index?api-version={_API}", {"value": batch})
            batch = []
    if batch:
        _req(token, "POST", f"indexes/{_INDEX}/docs/index?api-version={_API}", {"value": batch})

    _set_option(token, index, "enabled")
    print(f"✓ stamped {len(docs)} docs {dict(tally)}; query-time trimming ENABLED")


if __name__ == "__main__":
    setup_acl()
