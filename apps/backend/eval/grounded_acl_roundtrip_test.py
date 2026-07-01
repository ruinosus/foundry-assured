"""Chunk 4 — per-user ACL round-trip over the GROUNDED path (Responses + MCP + x-ms-query-source-authorization).

The proof the slice exists for: run the grounded Responses call as User A (in the `confidential`
group) and User B (public-only) — same probe query — and assert **A cites the confidential doc and
B does NOT** (spec §5: "B lacks the confidential citation that A has", so a trivial B-declines can't
fake a pass). Primary MCP auth = the app's search token (Search Index Data Reader); the per-user ACL
comes from each caller's token in the `x-ms-query-source-authorization` header.

Infra-gated — skips cleanly unless these are set:
  ENTRA_TENANT_ID, COCKPIT_TEST_USER_A, COCKPIT_TEST_USER_B, COCKPIT_TEST_PASSWORD,
  COCKPIT_CONFIDENTIAL_SOURCE (the confidential doc's filename substring), AZURE_SEARCH_ENDPOINT,
  FOUNDRY_PROJECT_ENDPOINT. Prereq: eval.cockpit_acl_stamp_test green (cockpit-kb stamped).

    cd apps/backend && uv run python -m eval.grounded_acl_roundtrip_test
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import urllib.parse
import urllib.request

from azure.identity.aio import DefaultAzureCredential

from app.core.settings import settings
from app.core.tenant import tenant_config
from app.services.grounded import GroundedDomain, build_responses_kwargs

_SEARCH_SCOPE = "https://search.azure.com/.default"
_ROPC_CLIENT = "04b07795-8ddb-461a-bbee-02f9e1bf7b46"  # Azure CLI public client (ROPC, test only)
_PROBE = os.environ.get(
    "COCKPIT_ACL_PROBE", "Descreva a arquitetura confidencial e as métricas do cockpit."
)


def _ropc_token(upn: str, password: str) -> str:
    body = urllib.parse.urlencode({
        "grant_type": "password", "client_id": _ROPC_CLIENT, "scope": _SEARCH_SCOPE,
        "username": upn, "password": password,
    }).encode()
    url = f"https://login.microsoftonline.com/{settings.entra_tenant_id}/oauth2/v2.0/token"
    with urllib.request.urlopen(urllib.request.Request(url, data=body), timeout=60) as r:
        return json.load(r)["access_token"]


async def _sources_as(user_token: str, domain: GroundedDomain, primary_token: str, client) -> set[str]:
    """Run the grounded Responses call with the caller's ACL token; return the cited source filenames."""
    # build the kwargs, then override the ACL header with THIS user's token (primary auth stays the app's).
    kwargs = build_responses_kwargs(_PROBE, domain, model=tenant_config().foundry_model, search_token=primary_token)
    kwargs["tools"][0]["headers"] = {"x-ms-query-source-authorization": user_token}
    kwargs["stream"] = False
    resp = await client.responses.create(**kwargs)
    out: set[str] = set()
    for item in getattr(resp, "output", []) or []:
        for c in getattr(item, "content", []) or []:
            for a in (getattr(c, "annotations", None) or []):
                d = a if isinstance(a, dict) else (a.model_dump() if hasattr(a, "model_dump") else {})
                url = (d.get("url") or "")
                if url and not url.startswith("mcp://"):
                    out.add(url.rsplit("/", 1)[-1])
    return out


async def _run() -> int:
    pw = os.environ.get("COCKPIT_TEST_PASSWORD", "")
    a, b = os.environ.get("COCKPIT_TEST_USER_A", ""), os.environ.get("COCKPIT_TEST_USER_B", "")
    conf = os.environ.get("COCKPIT_CONFIDENTIAL_SOURCE", "")
    cfg = tenant_config()
    if not (pw and a and b and conf and cfg.azure_search_endpoint and cfg.foundry_project_endpoint):
        print("⏭️  SKIP: ACL round-trip needs COCKPIT_TEST_USER_A/B + password + "
              "COCKPIT_CONFIDENTIAL_SOURCE + live infra.")
        return 0

    domain = GroundedDomain(
        kb_name=cfg.cockpit_search_knowledge_base, instructions="Use a base e cite.",
        acl=True, search_endpoint=cfg.azure_search_endpoint,
    )
    from azure.ai.projects.aio import AIProjectClient

    cred = DefaultAzureCredential()
    proj = AIProjectClient(endpoint=cfg.foundry_project_endpoint, credential=cred, allow_preview=True)
    try:
        primary = (await cred.get_token(_SEARCH_SCOPE)).token  # app identity (Search Index Data Reader)
        client = proj.get_openai_client()
        client = await client if asyncio.iscoroutine(client) else client
        src_a = await _sources_as(_ropc_token(a, pw), domain, primary, client)
        src_b = await _sources_as(_ropc_token(b, pw), domain, primary, client)
    finally:
        import contextlib
        for o in (proj, cred):
            with contextlib.suppress(Exception):
                await o.close()

    a_has = any(conf in s for s in src_a)
    b_has = any(conf in s for s in src_b)
    print(f"User A cited sources: {sorted(src_a)}")
    print(f"User B cited sources: {sorted(src_b)}")
    print(f"confidential='{conf}' → A_has={a_has} B_has={b_has}")

    if not a_has:
        print("❌ FAIL: cleared User A did NOT cite the confidential doc — the probe/classification "
              "doesn't route A to it (fix the fixture, spec §5).")
        return 1
    if b_has:
        print("❌ FAIL: public-only User B cited the confidential doc — ACL is NOT trimming (leak).")
        return 1
    print("✅ PASS: A cites the confidential doc, B does not — per-user document ACL enforced.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_run()))
