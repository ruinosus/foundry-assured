"""Task 10 (Part 1) — A-vs-B ACL round-trip THROUGH the unified `/cockpit` HTTP endpoint.

The final headless proof that per-user document ACL survives the WHOLE endpoint stack — not just
`retrieve()` in isolation (that's `eval.retrieval_acl_parity_test`), but the real HTTP path:

    POST /cockpit  →  auth dependency (bearer → User) → current_user() captured in the endpoint →
    stream_grounded(body, cockpit_domain, user)  →  retrieve() (native searchIndex retrieve +
    per-user x-ms-query-source-authorization OBO token) → synthesize → the AG-UI `sources` CUSTOM event.

For each of two REAL Entra users we POST the same grounded probe to the LIVE unified `/cockpit`
endpoint (default: local `http://localhost:8000`, the exact production code path) and assert on the
CITED SOURCE FILENAMES in the `sources` CustomEvent — NOT the answer prose. Hard lesson: B's prose can
mention the topic "telemetria" without CITING the confidential doc; only the source set is the ACL fact.
  - User A (confidential group) MUST cite COCKPIT_CONFIDENTIAL_SOURCE (`cockpit-mcp-telemetry`).
  - User B (public-only) MUST NOT.

Token flow (mirrors eval.grounded_deployed_roundtrip_test): confidential ROPC — the API app requests a
token for ITSELF (`scope={api}/.default`, `grant_type=password`) on behalf of each test user. That token
has audience = the API app (exactly what the SPA sends), so the backend auth dependency validates it and
`stream_grounded` OBO-exchanges it downstream for the inference + search tokens. RULE #2: keyless for the
product path; the ROPC/test-user tokens are TEST-ONLY, via the confidential client, never printed.

Infra-gated — skips cleanly unless these are set (test-user creds + API secret read from .env via
pydantic, since they aren't exported to os.environ):
  ENTRA_TENANT_ID, ENTRA_API_CLIENT_ID, ENTRA_API_CLIENT_SECRET,
  COCKPIT_TEST_USER_A, COCKPIT_TEST_USER_B, COCKPIT_TEST_PASSWORD, COCKPIT_CONFIDENTIAL_SOURCE.
Optional: BACKEND_URL (defaults to http://localhost:8000 — start it with
  `cd apps/backend && uv run uvicorn app.main:app --port 8000`).

    cd apps/backend && uv run python -m eval.grounded_archetype_roundtrip_test

Exit codes: 0 ✅ A cites confidential / B does not (or SKIP) · 1 RUN_ERROR / empty answer / leak / A missing.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request

from pydantic_settings import BaseSettings, SettingsConfigDict


class _Creds(BaseSettings):
    """Secrets + test-user creds live in .env (pydantic doesn't push them to os.environ)."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    entra_tenant_id: str = ""
    entra_api_client_id: str = ""
    entra_api_client_secret: str = ""
    cockpit_test_user_a: str = ""
    cockpit_test_user_b: str = ""
    cockpit_test_password: str = ""
    cockpit_confidential_source: str = ""
    cockpit_acl_probe: str = "Como funciona a telemetria e a observabilidade do Cockpit?"


def _post_form(url: str, data: dict) -> dict:
    req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode())
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def _user_api_token(tid: str, api: str, secret: str, upn: str, pw: str) -> str:
    """Confidential ROPC: the API app requests a token for ITSELF (`{api}/.default`) on behalf of the
    user via password grant — audience = the API app, i.e. exactly what the SPA would send and what the
    backend auth dependency validates + OBO-exchanges. TEST-ONLY. Never printed."""
    return _post_form(
        f"https://login.microsoftonline.com/{tid}/oauth2/v2.0/token",
        {"grant_type": "password", "client_id": api, "client_secret": secret,
         "scope": f"{api}/.default", "username": upn, "password": pw},
    )["access_token"]


def _ask(backend: str, token: str, probe: str) -> tuple[int, list[str], str | None]:
    """POST the grounded turn to the LIVE /cockpit; return (answer_chars, cited_sources, run_error).

    Consumes the AG-UI SSE stream: TEXT_MESSAGE_CONTENT deltas → char count (liveness), the `sources`
    CUSTOM event → the CITED source filenames (the ACL fact), RUN_ERROR → surfaced verbatim."""
    body = {"messages": [{"role": "user", "content": probe}]}
    req = urllib.request.Request(
        f"{backend.rstrip('/')}/cockpit", method="POST", data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                 "Accept": "text/event-stream"},
    )
    chars, sources, err = 0, [], None
    with urllib.request.urlopen(req, timeout=180) as r:
        for raw in r:
            line = raw.decode(errors="replace").strip()
            if not line.startswith("data:"):
                continue
            try:
                ev = json.loads(line[5:].strip())
            except json.JSONDecodeError:
                continue
            t = ev.get("type")
            if t == "TEXT_MESSAGE_CONTENT":
                chars += len(ev.get("delta", ""))
            elif t == "CUSTOM" and ev.get("name") == "sources":
                sources = [s.get("source", "") for s in (ev.get("value") or [])]
            elif t == "RUN_ERROR":
                err = ev.get("message")
    return chars, sources, err


def main() -> int:
    c = _Creds()
    backend = os.environ.get("BACKEND_URL", "http://localhost:8000")
    tid, api, secret = c.entra_tenant_id, c.entra_api_client_id, c.entra_api_client_secret
    a, b, pw, conf = (
        c.cockpit_test_user_a, c.cockpit_test_user_b, c.cockpit_test_password, c.cockpit_confidential_source,
    )
    probe = os.environ.get("COCKPIT_ACL_PROBE") or c.cockpit_acl_probe

    if not all([tid, api, secret, a, b, pw, conf]):
        print("⏭️  SKIP: unified /cockpit round-trip needs ENTRA_TENANT_ID + ENTRA_API_CLIENT_ID/SECRET "
              "+ COCKPIT_TEST_USER_A/B + COCKPIT_TEST_PASSWORD + COCKPIT_CONFIDENTIAL_SOURCE.")
        return 0

    print(f"unified /cockpit A-vs-B round-trip @ {backend.rstrip('/')}/cockpit, probe='{probe}'")
    print(f"confidential-source substring: '{conf}'\n")

    ca, sa, ea = _ask(backend, _user_api_token(tid, api, secret, a, pw), probe)
    cb, sb, eb = _ask(backend, _user_api_token(tid, api, secret, b, pw), probe)
    a_has = any(conf in s for s in sa)
    b_has = any(conf in s for s in sb)
    print(f"User A: {ca} answer-chars, err={ea}, {len(sa)} sources, cites '{conf}'={a_has} -> {sorted(set(sa))}")
    print(f"User B: {cb} answer-chars, err={eb}, {len(sb)} sources, cites '{conf}'={b_has} -> {sorted(set(sb))}")

    if ea or eb:
        print(f"\n❌ FAIL: RUN_ERROR on the live /cockpit (A={ea!r} B={eb!r}) — the grounded endpoint errored.")
        return 1
    if not (ca and cb):
        print("\n❌ FAIL: an answer came back empty — the synthesis didn't stream through the endpoint.")
        return 1
    if not a_has:
        print("\n❌ FAIL: cleared User A did NOT cite the confidential doc THROUGH /cockpit — "
              "endpoint auth / OBO / retrieve() / sources-event is broken.")
        return 1
    if b_has:
        print("\n❌ FAIL: public-only User B cited the confidential doc THROUGH /cockpit — ACL LEAK.")
        return 1
    print("\n✅ PASS: the unified /cockpit endpoint enforces per-user document ACL end-to-end — "
          "A cites the confidential doc, B does not (no 403, no leak).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
