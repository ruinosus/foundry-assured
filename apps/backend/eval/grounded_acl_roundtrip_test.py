"""Chunk 4 — per-user ACL round-trip over the GROUNDED cockpit path (Option A: direct-search + trim).

The proof the slice exists for: run the ACL-trimmed retrieval as User A (in the `confidential` group)
and User B (public-only) — same probe — and assert **A gets the confidential doc and B does NOT**
(spec §5: "B lacks the confidential doc that A has", so a trivial B-declines can't fake a pass).

This exercises the exact path the live `/cockpit` uses (app/services/grounded._direct_search_authorized):
a DIRECT search as each user, where `x-ms-query-source-authorization` trims by the stamped `groups`
field. (The agentic knowledge_base_retrieve path does NOT trim — azure-sdk#44454 — which is why the
cockpit path retrieves + trims app-side and synthesizes only from the authorized docs.)

Infra-gated — skips cleanly unless these are set:
  ENTRA_TENANT_ID, COCKPIT_TEST_USER_A, COCKPIT_TEST_USER_B, COCKPIT_TEST_PASSWORD,
  COCKPIT_CONFIDENTIAL_SOURCE (the confidential doc's filename substring), AZURE_SEARCH_ENDPOINT.
Prereq: cockpit-kb stamped (eval.cockpit_acl_stamp_test green).

    cd apps/backend && uv run python -m eval.grounded_acl_roundtrip_test
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import urllib.parse
import urllib.request

from azure.identity import DefaultAzureCredential

from app.core.settings import settings
from app.core.tenant import tenant_config
from app.services.grounded import GroundedDomain, _direct_search_authorized

_SEARCH_SCOPE = "https://search.azure.com/.default"
_ROPC_CLIENT = "04b07795-8ddb-461a-bbee-02f9e1bf7b46"  # Azure CLI public client (ROPC, test only)
_PROBE = os.environ.get("COCKPIT_ACL_PROBE", "telemetria e observabilidade do cockpit")


def _ropc_token(upn: str, password: str) -> str:
    body = urllib.parse.urlencode({
        "grant_type": "password", "client_id": _ROPC_CLIENT, "scope": _SEARCH_SCOPE,
        "username": upn, "password": password,
    }).encode()
    url = f"https://login.microsoftonline.com/{settings.entra_tenant_id}/oauth2/v2.0/token"
    with urllib.request.urlopen(urllib.request.Request(url, data=body), timeout=60) as r:
        return json.load(r)["access_token"]


async def _run() -> int:
    pw = os.environ.get("COCKPIT_TEST_PASSWORD", "")
    a, b = os.environ.get("COCKPIT_TEST_USER_A", ""), os.environ.get("COCKPIT_TEST_USER_B", "")
    conf = os.environ.get("COCKPIT_CONFIDENTIAL_SOURCE", "")
    cfg = tenant_config()
    if not (pw and a and b and conf and cfg.azure_search_endpoint):
        print("⏭️  SKIP: ACL round-trip needs COCKPIT_TEST_USER_A/B + password + "
              "COCKPIT_CONFIDENTIAL_SOURCE + AZURE_SEARCH_ENDPOINT.")
        return 0

    domain = GroundedDomain(
        kb_name=cfg.cockpit_search_knowledge_base, instructions="X", acl=True,
        search_endpoint=cfg.azure_search_endpoint, search_index=cfg.cockpit_search_index,
    )
    primary = DefaultAzureCredential().get_token(_SEARCH_SCOPE).token  # app identity (Search Index Data Reader)

    async def authorized_sources(upn: str) -> list[str]:
        docs = await _direct_search_authorized(domain, _PROBE, primary, _ropc_token(upn, pw), top=8)
        return [d["source"] for d in docs]

    src_a = await authorized_sources(a)
    src_b = await authorized_sources(b)
    a_has = any(conf in s for s in src_a)
    b_has = any(conf in s for s in src_b)
    print(f"User A ({len(src_a)} docs) cites confidential '{conf}': {a_has} -> {sorted(src_a)}")
    print(f"User B ({len(src_b)} docs) cites confidential '{conf}': {b_has} -> {sorted(src_b)}")

    if not a_has:
        print("❌ FAIL: cleared User A did NOT get the confidential doc — the probe/classification "
              "doesn't route A to it (fix the fixture, spec §5).")
        return 1
    if b_has:
        print("❌ FAIL: public-only User B got the confidential doc — ACL is NOT trimming (leak).")
        return 1
    print("✅ PASS: A retrieves the confidential doc, B does not — per-user document ACL enforced "
          "(fail-closed; the model only ever synthesizes from the authorized set).")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_run()))
