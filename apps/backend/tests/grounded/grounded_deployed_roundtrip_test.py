"""Deployed end-to-end ACL round-trip — hits the DEPLOYED /cockpit as real users (OBO), no browser.

The definitive proof the whole stack works in the cloud: for each test user, get a token for the API
app (confidential ROPC), POST it to the deployed backend /cockpit, consume the AG-UI stream, and
assert the grounded answer comes back WITHOUT a 403 (the contextvar/OBO/inference path works) and that
per-user ACL holds — A surfaces the confidential doc, B does not. More reliable than the browser E2E
(no MFA/timing flakiness); it exercises the exact deployed code path.

Infra-gated — skips cleanly unless set:
  BACKEND_URL (deployed backend), ENTRA_TENANT_ID, ENTRA_API_CLIENT_ID, ENTRA_API_CLIENT_SECRET,
  COCKPIT_TEST_USER_A, COCKPIT_TEST_USER_B, COCKPIT_TEST_PASSWORD, COCKPIT_CONFIDENTIAL_SOURCE.

    cd apps/backend && uv run python -m eval.grounded_deployed_roundtrip_test
"""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request

_PROBE = os.environ.get("COCKPIT_ACL_PROBE", "Como funciona a telemetria e a observabilidade do Cockpit?")


def _post_form(url: str, data: dict) -> dict:
    req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode())
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def _user_api_token(tid: str, api: str, secret: str, upn: str, pw: str) -> str:
    # Confidential ROPC: the API app requests a token for ITSELF (GUID scope) on behalf of the user
    # via password grant — a token with audience = the API app, i.e. what the SPA would send.
    return _post_form(
        f"https://login.microsoftonline.com/{tid}/oauth2/v2.0/token",
        {"grant_type": "password", "client_id": api, "client_secret": secret,
         "scope": f"{api}/.default", "username": upn, "password": pw},
    )["access_token"]


def _ask_deployed(backend: str, token: str) -> tuple[int, list[str], str | None]:
    """POST the grounded turn to the deployed /cockpit; return (answer_chars, cited_sources, run_error)."""
    body = {"messages": [{"role": "user", "content": _PROBE}]}
    req = urllib.request.Request(
        f"{backend.rstrip('/')}/cockpit", method="POST", data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "text/event-stream"},
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


def main() -> None:
    backend = os.environ.get("BACKEND_URL", "")
    tid = os.environ.get("ENTRA_TENANT_ID", "")
    api = os.environ.get("ENTRA_API_CLIENT_ID", "")
    secret = os.environ.get("ENTRA_API_CLIENT_SECRET", "")
    a, b = os.environ.get("COCKPIT_TEST_USER_A", ""), os.environ.get("COCKPIT_TEST_USER_B", "")
    pw, conf = os.environ.get("COCKPIT_TEST_PASSWORD", ""), os.environ.get("COCKPIT_CONFIDENTIAL_SOURCE", "")
    if not all([backend, tid, api, secret, a, b, pw, conf]):
        print("⏭️  SKIP: deployed round-trip needs BACKEND_URL + ENTRA_API_* + COCKPIT_TEST_* + CONFIDENTIAL_SOURCE.")
        sys.exit(0)

    ca, sa, ea = _ask_deployed(backend, _user_api_token(tid, api, secret, a, pw))
    cb, sb, eb = _ask_deployed(backend, _user_api_token(tid, api, secret, b, pw))
    a_has = any(conf in s for s in sa)
    b_has = any(conf in s for s in sb)
    print(f"A: {ca} chars, err={ea}, {len(sa)} sources, cites '{conf}'={a_has}")
    print(f"B: {cb} chars, err={eb}, {len(sb)} sources, cites '{conf}'={b_has}")

    if ea or eb:
        print(f"❌ FAIL: RUN_ERROR on the deployed backend (A={ea!r} B={eb!r}) — the grounded path errored.")
        sys.exit(1)
    if not (ca and cb):
        print("❌ FAIL: an answer came back empty — the synthesis didn't stream.")
        sys.exit(1)
    if not a_has:
        print("❌ FAIL: cleared A did not surface the confidential doc.")
        sys.exit(1)
    if b_has:
        print("❌ FAIL: public-only B surfaced the confidential doc — ACL leak.")
        sys.exit(1)
    print("✅ PASS: deployed /cockpit answers both users (no 403), A cites the confidential doc, B does not.")
    sys.exit(0)


if __name__ == "__main__":
    main()
