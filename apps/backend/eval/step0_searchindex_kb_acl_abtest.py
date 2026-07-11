"""Task 2b A-vs-B gate — per-user ACL over the NATIVE agentic retrieve on the PROVISIONED
searchIndex cockpit KB (`cockpit-si-kb` → `cockpit-docbundles-si-ks` over the EXISTING
ACL-stamped `cockpit-docbundles-ks-index`).

Unlike step0_searchindex_filter_probe (which used only the single app/dev token available in a
non-interactive shell and so could only confirm the confidential doc is *reachable* via the header),
this runs the REAL A-vs-B trim: it acquires a search-scoped token for User A (confidential group) and
User B (public-only) via ROPC and calls the native KB `retrieve` on the already-provisioned
searchIndex KB with each token as `x-ms-query-source-authorization`. It asserts A cites the
confidential source and B does NOT — the exact per-user trim the header carries, now on the native
agentic path over the searchIndex KB.

It does NOT create or tear down any KB — it targets the KB that ingest_docbundles provisioned (default
cfg.cockpit_searchindex_knowledge_base / _knowledge_source). Reuses the probe's proven native-retrieve
helpers (RULE #1). Read-only against live infra.

Infra-gated — skips cleanly unless these are set (test-user creds read from .env via pydantic, since
they aren't exported to os.environ):
  ENTRA_TENANT_ID, COCKPIT_TEST_USER_A, COCKPIT_TEST_USER_B, COCKPIT_TEST_PASSWORD,
  COCKPIT_CONFIDENTIAL_SOURCE, AZURE_SEARCH_ENDPOINT.

    cd apps/backend && uv run python -m eval.step0_searchindex_kb_acl_abtest

Exit codes: 0 ✅ A cites confidential / B does not (or SKIP) · 1 leak (B has it) or A missing it ·
2 retrieve rejected.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import urllib.parse
import urllib.request

from azure.identity import DefaultAzureCredential
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.settings import settings
from app.core.tenant import tenant_config

# Reuse the proven native-retrieve helpers from the STEP 0.5 probe (RULE #1 — don't reinvent shapes).
from eval.step0_searchindex_filter_probe import (
    _RETRIEVE_API,
    _retrieve,
    _sources_from_response,
)

_SEARCH_SCOPE = "https://search.azure.com/.default"
_ROPC_CLIENT = "04b07795-8ddb-461a-bbee-02f9e1bf7b46"  # Azure CLI public client (ROPC, test only)


class _Creds(BaseSettings):
    """Test-user creds live in .env (pydantic doesn't push them to os.environ)."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    cockpit_test_user_a: str = ""
    cockpit_test_user_b: str = ""
    cockpit_test_password: str = ""
    cockpit_confidential_source: str = ""
    cockpit_acl_probe: str = "telemetria e observabilidade do cockpit"


def _ropc_token(upn: str, password: str) -> str:
    body = urllib.parse.urlencode({
        "grant_type": "password", "client_id": _ROPC_CLIENT, "scope": _SEARCH_SCOPE,
        "username": upn, "password": password,
    }).encode()
    url = f"https://login.microsoftonline.com/{settings.entra_tenant_id}/oauth2/v2.0/token"
    with urllib.request.urlopen(urllib.request.Request(url, data=body), timeout=60) as r:
        return json.load(r)["access_token"]


async def _run() -> int:
    c = _Creds()
    cfg = tenant_config()
    a, b, pw, conf = (
        c.cockpit_test_user_a, c.cockpit_test_user_b, c.cockpit_test_password, c.cockpit_confidential_source,
    )
    search = (cfg.azure_search_endpoint or "").rstrip("/")
    kb = cfg.cockpit_searchindex_knowledge_base
    ks = cfg.cockpit_searchindex_knowledge_source
    probe_text = os.environ.get("COCKPIT_ACL_PROBE") or c.cockpit_acl_probe

    if not (a and b and pw and conf and search):
        print("⏭️  SKIP: needs COCKPIT_TEST_USER_A/B + password + COCKPIT_CONFIDENTIAL_SOURCE + "
              "AZURE_SEARCH_ENDPOINT.")
        return 0

    print(f"Native retrieve A-vs-B on searchIndex KB '{kb}' (ks '{ks}'), probe='{probe_text}'")
    print(f"confidential-source substring: '{conf}'\n")

    service_token = DefaultAzureCredential().get_token(_SEARCH_SCOPE).token  # app identity (Search Index Data Reader)

    def user_sources(upn: str) -> tuple[int, list[str], list]:
        tok = _ropc_token(upn, pw)
        # Patch the module-level probe text the shared _retrieve uses, so both users query the same thing.
        import eval.step0_searchindex_filter_probe as p
        p._PROBE_TEXT = probe_text
        status, body = _retrieve(search, kb, ks, _RETRIEVE_API, service_token, user_token=tok)
        counts = [act.get("count") for act in (body.get("activity") or []) if act.get("type") == "searchIndex"]
        return status, _sources_from_response(body), counts

    sa, src_a, cnt_a = user_sources(a)
    sb, src_b, cnt_b = user_sources(b)
    if sa not in (200, 206) or sb not in (200, 206):
        print(f"❌ retrieve rejected (A status={sa}, B status={sb}).")
        return 2

    a_has = any(conf in s for s in src_a)
    b_has = any(conf in s for s in src_b)
    print(f"User A ({len(src_a)} carriers, subquery_counts={cnt_a}) cites confidential '{conf}': {a_has}")
    print(f"User B ({len(src_b)} carriers, subquery_counts={cnt_b}) cites confidential '{conf}': {b_has}")

    if not a_has:
        print("❌ FAIL: cleared User A did NOT get the confidential doc via the native searchIndex "
              "retrieve — header trim or fixture issue.")
        return 1
    if b_has:
        print("❌ FAIL: public-only User B got the confidential doc — the native searchIndex retrieve is "
              "NOT trimming per-user (leak). DO NOT cut over.")
        return 1
    print("\n✅ PASS: on the searchIndex KB, native agentic retrieve honors the per-user ACL header — "
          "A retrieves the confidential doc, B does not. Safe to cut cockpit over to it.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_run()))
