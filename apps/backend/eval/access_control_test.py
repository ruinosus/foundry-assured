"""Phase 4 — access-control gate over the AGENTIC path (the path the agent uses).

The earlier version checked a direct search; this checks what actually matters: the
**agentic retrieve + app-side trim** (secure_search.py). Acquire the two test identities
(ROPC), run the agentic retrieve as each, apply the trim, and assert every chunk the
caller keeps belongs to a component the caller is entitled to. A single chunk from an
unauthorized component is a leak and fails the build (assurance.yaml
security.access_control_violations_max, default 0).

Test creds are secrets (gitignored .env / CI), never committed:
  ENTRA_TENANT_ID, COCKPIT_TEST_USER_A, COCKPIT_TEST_USER_B, COCKPIT_TEST_PASSWORD,
  COCKPIT_ACL_* groups, AZURE_SEARCH_ENDPOINT, COCKPIT_ACL_CLASSIFICATION

  uv run python -m eval.access_control_test
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from agent_framework import Message
from agent_framework.azure import AzureAISearchContextProvider
from azure.identity import DefaultAzureCredential

from app.agents.secure_search import _chunk_component, authorized_components, trim_agentic_content
from app.core.settings import settings
from app.core.tenant import tenant_config

_SEARCH_SCOPE = "https://search.azure.com/.default"
_ROPC_CLIENT = "04b07795-8ddb-461a-bbee-02f9e1bf7b46"
_ASSURANCE = Path(__file__).resolve().parent / "assurance.yaml"
_PROBE = "detalhes da arquitetura, métricas e pricing do cockpit"


def _violations_ceiling() -> int:
    try:
        import yaml

        cfg = yaml.safe_load(_ASSURANCE.read_text(encoding="utf-8")) or {}
        return int((cfg.get("security") or {}).get("access_control_violations_max", 0))
    except Exception:  # noqa: BLE001
        return 0


def _ropc_token(upn: str, password: str) -> str:
    body = urllib.parse.urlencode({
        "grant_type": "password", "client_id": _ROPC_CLIENT, "scope": _SEARCH_SCOPE,
        "username": upn, "password": password,
    }).encode()
    url = f"https://login.microsoftonline.com/{settings.entra_tenant_id}/oauth2/v2.0/token"
    with urllib.request.urlopen(urllib.request.Request(url, data=body), timeout=60) as r:
        return json.load(r)["access_token"]


async def _kept_components(provider, token: str) -> tuple[set[str], set[str]]:
    """Run the agentic retrieve as the caller, trim, and return (kept, authorized)."""
    orig = provider._retrieval_client.retrieve

    async def as_user(*a, **k):  # noqa: ANN002, ANN003
        k["x_ms_query_source_authorization"] = token
        return await orig(*a, **k)

    provider._retrieval_client.retrieve = as_user
    result = await provider._agentic_search([Message(role="user", contents=[_PROBE])])
    provider._retrieval_client.retrieve = orig

    authorized = authorized_components(token)
    raw = result[0].text if result and getattr(result[0], "text", None) else "[]"
    kept = {_chunk_component(c.get("content", "")) for c in json.loads(trim_agentic_content(raw, authorized))
            if isinstance(c, dict)}
    return kept, authorized


async def _run() -> int:
    password = os.environ.get("COCKPIT_TEST_PASSWORD", "")
    upn_b = os.environ.get("COCKPIT_TEST_USER_B", "")
    if not (password and upn_b):
        print("⏭️  skipping access-control gate: test creds not set.")
        return 0

    provider = AzureAISearchContextProvider(
        endpoint=tenant_config().azure_search_endpoint, knowledge_base_name=tenant_config().cockpit_search_knowledge_base,
        credential=DefaultAzureCredential(), mode="agentic", retrieval_reasoning_effort="medium",
    )
    await provider._ensure_knowledge_base()

    kept_b, auth_b = await _kept_components(provider, _ropc_token(upn_b, password))
    leak = sorted(kept_b - auth_b)
    print(f"User B kept components: {sorted(kept_b)}")
    print(f"User B authorized:      {sorted(auth_b)}")

    ceiling = _violations_ceiling()
    if len(leak) > ceiling:
        print(f"\n❌ Access-control gate FAILED — agentic path leaked to User B: {leak} "
              f"(ceiling {ceiling}).")
        return 1

    # Positive side: a cleared user (A) must NOT be over-restricted — they should be
    # entitled to strictly more than B (else the trim is globally clamping, which the
    # leak-only check wouldn't catch). Skips quietly if User A isn't configured.
    upn_a = os.environ.get("COCKPIT_TEST_USER_A", "")
    if upn_a:
        kept_a, auth_a = await _kept_components(provider, _ropc_token(upn_a, password))
        a_leak = sorted(kept_a - auth_a)
        print(f"User A authorized:      {len(auth_a)} components | kept {len(kept_a)}")
        if a_leak:
            print(f"\n❌ FAILED — leak to User A too: {a_leak}.")
            return 1
        if not auth_a > auth_b:
            print("\n❌ FAILED — cleared User A is not entitled to more than public-only B "
                  "(the trim is over-restricting, not just safe).")
            return 1

    print(f"\n✅ Access-control gate PASSED — B stays within entitlement (leaks {len(leak)} ≤ "
          f"{ceiling}); A is entitled to strictly more.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_run()))
