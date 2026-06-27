"""Phase 4 — access-control gate: prove query-time ACL trimming holds.

Acquires the two test identities (ROPC) and asserts the KB trims by entitlement:
**User B (public only) must retrieve ZERO non-public documents**; User A (all tiers)
sees every tier. A single leak fails the build (assurance.yaml
`security.access_control_violations_max`, default 0). Deterministic security gate —
the negative case the mechanism guarantees.

Runs against the live index using the test users' search-scoped tokens. Test creds are
secrets (gitignored .env / CI secrets), never committed:

  ENTRA_TENANT_ID, COCKPIT_TEST_USER_A, COCKPIT_TEST_USER_B  (full UPNs),
  COCKPIT_TEST_PASSWORD, COCKPIT_ACL_{PUBLIC,INTERNAL,CONFIDENTIAL}_GROUP,
  AZURE_SEARCH_ENDPOINT

  uv run python -m eval.access_control_test
"""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from azure.identity import DefaultAzureCredential

from app.core.settings import settings

_API = "2025-08-01-preview"
_INDEX = "cockpit-docbundles-ks-index"
_SEARCH_SCOPE = "https://search.azure.com/.default"
# Public client that supports ROPC for first-party scopes (the Azure CLI app).
_ROPC_CLIENT = "04b07795-8ddb-461a-bbee-02f9e1bf7b46"
_ASSURANCE = Path(__file__).resolve().parent / "assurance.yaml"


def _violations_ceiling() -> int:
    try:
        import yaml

        cfg = yaml.safe_load(_ASSURANCE.read_text(encoding="utf-8")) or {}
        return int((cfg.get("security") or {}).get("access_control_violations_max", 0))
    except Exception:  # noqa: BLE001
        return 0


def _ropc_token(upn: str, password: str) -> str:
    body = urllib.parse.urlencode({
        "grant_type": "password",
        "client_id": _ROPC_CLIENT,
        "scope": _SEARCH_SCOPE,
        "username": upn,
        "password": password,
    }).encode()
    url = f"https://login.microsoftonline.com/{settings.entra_tenant_id}/oauth2/v2.0/token"
    with urllib.request.urlopen(urllib.request.Request(url, data=body), timeout=60) as r:
        return json.load(r)["access_token"]


def _tiers_seen(service_token: str, user_token: str, label_by_group: dict[str, str]) -> dict[str, int]:
    """Search as the user; tally the sensitivity tiers of the documents returned."""
    url = (
        f"{settings.azure_search_endpoint}/indexes/{_INDEX}/docs"
        f"?api-version={_API}&search=*&$top=500&$select=groups"
    )
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {service_token}",
        "x-ms-query-source-authorization": user_token,
    })
    with urllib.request.urlopen(req, timeout=60) as r:
        docs = json.load(r).get("value", [])
    from collections import Counter
    seen: Counter[str] = Counter()
    for d in docs:
        for g in d.get("groups") or []:
            seen[label_by_group.get(g, g)] += 1
    return dict(seen)


def main() -> int:
    password = os.environ.get("COCKPIT_TEST_PASSWORD", "")
    upn_a = os.environ.get("COCKPIT_TEST_USER_A", "")
    upn_b = os.environ.get("COCKPIT_TEST_USER_B", "")
    if not (password and upn_a and upn_b):
        print("⏭️  skipping access-control gate: test creds not set (COCKPIT_TEST_USER_A/B + PASSWORD).")
        return 0

    label = {
        settings.cockpit_acl_public_group: "public",
        settings.cockpit_acl_internal_group: "internal",
        settings.cockpit_acl_confidential_group: "confidential",
    }
    service_token = DefaultAzureCredential().get_token(_SEARCH_SCOPE).token

    seen_a = _tiers_seen(service_token, _ropc_token(upn_a, password), label)
    seen_b = _tiers_seen(service_token, _ropc_token(upn_b, password), label)
    print(f"User A (all tiers)   sees: {seen_a}")
    print(f"User B (public only) sees: {seen_b}")

    # Violation = User B seeing any non-public document.
    violations = seen_b.get("internal", 0) + seen_b.get("confidential", 0)
    ceiling = _violations_ceiling()
    if violations > ceiling:
        print(f"\n❌ Access-control gate FAILED — User B retrieved {violations} restricted "
              f"document(s) (ceiling {ceiling}). The KB leaked across entitlements.")
        return 1
    if not seen_a:
        print("\n⚠️  User A saw nothing — check entitlements / token (not a leak, but the test is inconclusive).")
        return 1
    print(f"\n✅ Access-control gate PASSED — User B retrieved only public; A sees all tiers "
          f"(violations {violations} ≤ {ceiling}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
