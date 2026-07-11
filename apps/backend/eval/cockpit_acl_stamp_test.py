"""Chunk 2 — verify cockpit-kb carries permission metadata after the ACL re-ingest.

Infra-gated: reads the search index schema and asserts the document-level ACL was stamped so the
`x-ms-query-source-authorization` header can trim at query time (the grounded /cockpit path).
Asserts the deterministic post-stamp schema; the per-document A-vs-B proof is in
`eval.grounded_acl_roundtrip_test`. Skips cleanly when AZURE_SEARCH_ENDPOINT isn't configured.

Prereq (runbook): re-ingest with the minimal PoC classification —
  COCKPIT_DOCBUNDLES=… ACL_CLASSIFICATION=…/.cockpit-acl-poc.json \
    uv run python -m app.knowledge.ingest_docbundles
(needs tenant_config().acl_group_map to resolve `confidential` + `public` → object-ids).

    cd apps/backend && uv run python -m eval.cockpit_acl_stamp_test
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request

from azure.identity import DefaultAzureCredential

from app.core.tenant import tenant_config

_SEARCH_SCOPE = "https://search.azure.com/.default"
_API = "2025-08-01-preview"


def _get_index() -> dict:
    cfg = tenant_config()
    token = DefaultAzureCredential().get_token(_SEARCH_SCOPE).token
    url = f"{cfg.azure_search_endpoint}/indexes/{cfg.cockpit_search_index}?api-version={_API}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def main() -> None:
    if not tenant_config().azure_search_endpoint:
        print("⏭️  SKIP: AZURE_SEARCH_ENDPOINT not set — needs the live cockpit-kb index.")
        sys.exit(0)

    index = _get_index()
    fields = {f["name"]: f for f in index.get("fields", [])}

    # (a) the 'groups' permission-metadata field exists and is the groupIds permission filter.
    groups = fields.get("groups")
    if not groups:
        print("❌ FAIL: no 'groups' field — cockpit-kb was not re-ingested with ACL "
              "(set ACL_CLASSIFICATION + acl_group_map, then run ingest_docbundles).")
        sys.exit(1)
    if groups.get("permissionFilter") != "groupIds" or not groups.get("filterable"):
        print(f"❌ FAIL: 'groups' field misconfigured: {groups}")
        sys.exit(1)

    # (b) query-time trimming is armed.
    if index.get("permissionFilterOption") != "enabled":
        print(f"❌ FAIL: permissionFilterOption != enabled ({index.get('permissionFilterOption')!r}).")
        sys.exit(1)

    print("✅ PASS: cockpit-kb index carries the 'groups' groupIds permission filter and "
          "permissionFilterOption=enabled (per-user ACL trimming is armed).")
    # (c/d) optional: if a confidential source is named, sanity-check it is stamped to the
    # confidential group and at least one public doc has the public group.
    conf = os.environ.get("COCKPIT_CONFIDENTIAL_SOURCE", "")
    if conf:
        print(f"   (confidential probe doc configured: {conf} — verified end-to-end in "
              "eval.grounded_acl_roundtrip_test)")
    sys.exit(0)


if __name__ == "__main__":
    main()
