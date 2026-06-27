"""Phase 4 — document-level ACL on the KB index (access follows the SOURCE).

The mechanism enforces access; it never invents it. There is **no classification logic
in this code** — no tiers, no markers, no component names. Each document's access is the
group(s) that can read its *source*, exactly like the corpus is the owner's data:

  • Bundle manifests carry ``groups`` (the repo's read teams), written by wiki_builder by
    inheriting each source repo's access — or, for sources with NATIVE ACLs (SharePoint,
    ADLS Gen2), Foundry IQ ingests the ACL automatically and this step isn't needed.
  • For plain-blob sources without manifests, an external map
    (``COCKPIT_ACL_CLASSIFICATION`` → ``{document-key: [group-name,…]}``, gitignored).
  • Group NAMES resolve to Entra object-IDs via ``settings.acl_group_map`` (the tenant's
    own groups). Documents with no declared access **fail-closed** (no group → nobody).

Groups are arbitrary (a GitHub team, an ADLS group), never a fixed tier. `_component()`
is deterministic identity extraction (the key to look up), not classification.

    COCKPIT_ACL_CLASSIFICATION=/path/to/access.json uv run python -m app.knowledge.acl_setup
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from pathlib import Path

from azure.identity import DefaultAzureCredential

from app.core.settings import settings

_API = "2025-08-01-preview"
_INDEX = "cockpit-docbundles-ks-index"
_SEARCH_SCOPE = "https://search.azure.com/.default"
_GUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


def _component(blob_url: str) -> str:
    """Deterministic identity from the blob naming convention (NOT classification).

    `<component>(-v<ver>)?__<page>.md` → `<component>`; `source__<NAME>__…` → `source__<NAME>`."""
    name = re.sub(r"\.md\d*$", "", blob_url.rsplit("/", 1)[-1])
    head = name.split("__")[0]
    if head == "source" and "__" in name:
        return "source__" + name.split("__")[1]
    return re.sub(r"-v[\d.]+.*$", "", head)


def _resolve(names: list[str]) -> list[str]:
    """Group names → Entra object-IDs (GUIDs pass through; unknown names dropped)."""
    group_map = settings.acl_group_map
    ids: list[str] = []
    for n in names:
        if _GUID.match(n):
            ids.append(n)
        elif n in group_map:
            ids.append(group_map[n])
    return ids


def _load_external() -> dict[str, list[str]]:
    """Owner-provided { document-key : [group-name,…] }. External + gitignored."""
    path = os.environ.get("COCKPIT_ACL_CLASSIFICATION", settings.cockpit_acl_classification)
    if not path:
        return {}
    return json.loads(Path(path).expanduser().read_text(encoding="utf-8"))


def _req(token: str, method: str, path: str, body: dict | None = None) -> dict | None:
    req = urllib.request.Request(
        f"{settings.azure_search_endpoint}/{path}", method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req, json.dumps(body).encode() if body is not None else None, timeout=90)
    try:
        return json.load(resp)
    except Exception:  # noqa: BLE001 — 204 No Content on index PUT
        return None


def _set_option(token: str, index: dict, state: str) -> None:
    index = {k: v for k, v in index.items() if not k.startswith("@odata")}
    index["permissionFilterOption"] = state  # "enabled" | "disabled"
    _req(token, "PUT", f"indexes/{_INDEX}?api-version={_API}", index)


def setup_acl(component_groups: dict[str, list[str]] | None = None) -> None:
    """Stamp each document's access groups and enable query-time trimming.

    component_groups: { component-key : [group-name-or-id,…] }, typically built from the
    bundle manifests by the ingest. When None, falls back to the external map."""
    access = component_groups if component_groups is not None else _load_external()
    default_groups = [g for g in settings.cockpit_acl_default_groups.split(",") if g.strip()]
    if not access:
        print(f"⚠️  no access map — every doc → default {default_groups or '[] (fail-closed)'}.")

    token = DefaultAzureCredential().get_token(_SEARCH_SCOPE).token
    index = _req(token, "GET", f"indexes/{_INDEX}?api-version={_API}")
    assert index is not None

    if "groups" not in {f["name"] for f in index["fields"]}:
        index["fields"].append({
            "name": "groups", "type": "Collection(Edm.String)",
            "filterable": True, "retrievable": True, "searchable": False,
            "permissionFilter": "groupIds",
        })
        _set_option(token, index, "enabled")
        index = _req(token, "GET", f"indexes/{_INDEX}?api-version={_API}")
        assert index is not None
        print("✓ permission field 'groups' added")

    # Populate under a disabled window (docs with no group are invisible when enforced).
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
    fail_closed = 0
    batch: list[dict] = []
    for d in docs:
        names = access.get(_component(d.get("blob_url", "")), default_groups)
        gids = _resolve(names)
        if not gids:
            fail_closed += 1
        for n in (names or ["<none>"]):
            tally[n] += 1
        batch.append({"@search.action": "mergeOrUpload", "uid": d["uid"], "groups": gids})
        if len(batch) >= 500:
            _req(token, "POST", f"indexes/{_INDEX}/docs/index?api-version={_API}", {"value": batch})
            batch = []
    if batch:
        _req(token, "POST", f"indexes/{_INDEX}/docs/index?api-version={_API}", {"value": batch})

    _set_option(token, index, "enabled")
    note = f" ({fail_closed} fail-closed — no resolvable group)" if fail_closed else ""
    print(f"✓ stamped {len(docs)} docs by source access {dict(tally)}{note}; trimming ENABLED")


if __name__ == "__main__":
    setup_acl()
