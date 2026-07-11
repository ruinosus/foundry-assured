"""Task 3 — A-vs-B ACL parity THROUGH the production retrieval seam `retrieve()`.

The prior gate (eval.step0_searchindex_kb_acl_abtest) proved the RAW searchIndex KB `retrieve`
endpoint trims per-user via the `x-ms-query-source-authorization` header. THIS test proves the same
trim survives through **retrieve()'s own code** — the header-attach branch, `_native_retrieve`, the
`docKey` → `{source,url,snippet}` parse, and the central `_project` dedup — catching bugs the
raw-endpoint test can't (a dropped header, a mangled docKey parse, a dedup that loses the confidential
carrier).

It uses the same two real ROPC users A (confidential group) + B (public-only) and calls the PRODUCTION
`retrieval.retrieve(query, user, domain)` for EACH, asserting on the RETURNED docs' `source` filenames:
A's include COCKPIT_CONFIDENTIAL_SOURCE, B's do NOT. That source set IS retrieve()'s output — no prose.

Token injection: `retrieve()` derives the per-user search token via `retrieval._user_search_token(user)`,
which does an OBO exchange from `user.access_token`. Our ROPC tokens are ALREADY search-scoped (not OBO
assertions), so we monkeypatch `retrieval._user_search_token` to return each user's ROPC search token
directly. This exercises the REAL `_native_retrieve` + header-attach + docKey-parse + `_project` code with
a genuine per-user token; only the OBO exchange (separately covered) is stubbed. The original is restored
in a `finally`.

Infra-gated — skips cleanly unless these are set (test-user creds read from .env via pydantic, since
they aren't exported to os.environ):
  ENTRA_TENANT_ID, COCKPIT_TEST_USER_A, COCKPIT_TEST_USER_B, COCKPIT_TEST_PASSWORD,
  COCKPIT_CONFIDENTIAL_SOURCE, AZURE_SEARCH_ENDPOINT, and the searchIndex KB name.
Prereq: the searchIndex cockpit KB provisioned + ACL-stamped (eval.step0_searchindex_kb_acl_abtest green).

    cd apps/backend && uv run python -m eval.retrieval_acl_parity_test

Exit codes: 0 ✅ A cites confidential / B does not (or SKIP) · 1 leak (B has it) or A missing it.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import urllib.parse
import urllib.request

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.settings import settings
from app.core.tenant import tenant_config
from app.services import retrieval

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


class _Dom:
    """Duck-typed domain stub (DomainSpec doesn't exist yet) exposing the searchIndex cockpit KB.

    retrieve() reads `.kb_name` (→ takes the native path), `.ks_name`, `.search_endpoint`,
    `.search_index`, `.instructions` via plain attribute access."""

    def __init__(self, cfg) -> None:
        self.kb_name = cfg.cockpit_searchindex_knowledge_base      # "cockpit-si-kb"
        self.ks_name = cfg.cockpit_searchindex_knowledge_source    # "cockpit-docbundles-si-ks"
        self.search_endpoint = cfg.azure_search_endpoint
        self.search_index = cfg.cockpit_search_index
        self.instructions = "Retrieve grounding data and cite sources by their ref_id."


async def _run() -> int:
    c = _Creds()
    cfg = tenant_config()
    a, b, pw, conf = (
        c.cockpit_test_user_a, c.cockpit_test_user_b, c.cockpit_test_password, c.cockpit_confidential_source,
    )
    probe = os.environ.get("COCKPIT_ACL_PROBE") or c.cockpit_acl_probe

    if not (a and b and pw and conf and cfg.azure_search_endpoint and cfg.cockpit_searchindex_knowledge_base):
        print("⏭️  SKIP: retrieve() ACL parity needs COCKPIT_TEST_USER_A/B + password + "
              "COCKPIT_CONFIDENTIAL_SOURCE + AZURE_SEARCH_ENDPOINT + searchIndex KB name.")
        return 0

    dom = _Dom(cfg)
    print(f"retrieve() A-vs-B parity on searchIndex KB '{dom.kb_name}' (ks '{dom.ks_name}'), "
          f"probe='{probe}'")
    print(f"confidential-source substring: '{conf}'\n")

    tok_a = _ropc_token(a, pw)
    tok_b = _ropc_token(b, pw)

    # Stub ONLY the OBO exchange: feed each user's ROPC search token straight into retrieve()'s
    # per-user-token seam, so the REAL _native_retrieve + header-attach + docKey-parse + _project run.
    _orig = retrieval._user_search_token

    def _patch(tok: str) -> None:
        async def _f(_user):  # signature matches _user_search_token(user)
            return tok
        retrieval._user_search_token = _f

    try:
        # `user=object()` — non-None so retrieve() takes the ACL branch; the patched
        # _user_search_token ignores it and returns the ROPC token.
        _patch(tok_a)
        docs_a = await retrieval.retrieve(probe, user=object(), domain=dom)
        _patch(tok_b)
        docs_b = await retrieval.retrieve(probe, user=object(), domain=dom)
    finally:
        retrieval._user_search_token = _orig

    src_a = {d["source"] for d in docs_a}
    src_b = {d["source"] for d in docs_b}
    a_has = any(conf in s for s in src_a)
    b_has = any(conf in s for s in src_b)
    print(f"User A ({len(docs_a)} docs) cites confidential '{conf}': {a_has} -> {sorted(src_a)}")
    print(f"User B ({len(docs_b)} docs) cites confidential '{conf}': {b_has} -> {sorted(src_b)}")

    if not a_has:
        print("❌ FAIL: cleared User A did NOT get the confidential doc THROUGH retrieve() — "
              "header-attach / _native_retrieve / docKey-parse / _project or fixture is broken.")
        return 1
    if b_has:
        print("❌ FAIL: public-only User B got the confidential doc THROUGH retrieve() — the "
              "production seam is NOT trimming per-user (LEAK).")
        return 1
    print("\n✅ PASS: retrieve()'s own code path enforces per-user document ACL end-to-end — "
          "A retrieves the confidential doc, B does not (fail-closed).")
    return 0


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    sys.exit(main())
