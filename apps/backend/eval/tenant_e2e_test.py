"""Chunk 3 — infra-gated E2E proof of per-tenant isolation.

Tests (a)–(e) require a live Azure environment with two Entra tenants and real ROPC
test users. When the required configuration is absent the module skips cleanly
(prints a skip note, exits 0) so a full offline eval sweep stays green.

== What the test proves ==
DEPLOYMENT_MODE=shared, two tenants seeded in InMemoryTenantStore, real tokens
acquired via ROPC for each tenant's test user:

  (a) Token from tenant A → resolve_tenant resolves A's TenantRecord; tenant_config()
      returns A's data-plane; current_tenant_id() == A's tid.
  (b) Token from tenant B → same checks for B (distinct from A).
  (c) Token whose tid is NOT in the store → resolve_tenant raises HTTPException(403).
  (d) Suspended tenant → 403.
  (e) memory_scope() returns f"{tidA}:{oidA}" for A and f"{tidB}:{oidB}" for B —
      different prefixes, never collide.
  (f) _iss_callable(tid) returns the expected per-tenant issuer URL.

== Required environment variables ==
The following env vars must ALL be set for the real assertions to run.
Set them in a .env file or CI secrets — never commit them.

  # Deployment mode gate
  DEPLOYMENT_MODE=shared

  # Tenant A — first Entra tenant
  TENANT_E2E_A_TID        The tenant/directory ID (GUID) for tenant A.
  TENANT_E2E_A_USER       UPN (email) of the ROPC test user in tenant A.
  TENANT_E2E_A_PASSWORD   Password of that test user.
  TENANT_E2E_A_OID        Object ID (GUID) of that test user in tenant A.

  # Tenant B — second Entra tenant (may be the same directory with a different user,
  #             but must have a different tid to prove isolation; use a second tenant
  #             or a second AAD directory).
  TENANT_E2E_B_TID        The tenant/directory ID (GUID) for tenant B.
  TENANT_E2E_B_USER       UPN of the ROPC test user in tenant B.
  TENANT_E2E_B_PASSWORD   Password of that test user.
  TENANT_E2E_B_OID        Object ID (GUID) of that test user in tenant B.

  # API app registration used to acquire the ROPC token (audience for the API).
  # Reused from the existing access_control_test convention.
  ENTRA_API_CLIENT_ID     The client_id of the backend API app registration (used as
                          the ROPC scope audience: api://<id>/access_as_user).
                          If absent, falls back to the well-known Azure CLI public
                          client 04b07795-8ddb-461a-bbee-02f9e1bf7b46 for token
                          acquisition against the default scope.

  (Optional — only needed if you want to test against the real TableStorageTenantStore
   instead of the InMemory seed. The test itself uses InMemory by default.)
  TENANT_STORE_ACCOUNT_URL  Azure Storage account URL for the control-plane store.

== Run ==
  uv run python -m eval.tenant_e2e_test

Skip note is printed when infra is absent; exit 0 either way.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from types import SimpleNamespace

from fastapi import HTTPException

from app.core import auth
from app.core.tenant import (
    MultiTenantConfigProvider,
    TenantConfig,
    current_tenant_id,
    set_current_tenant,
    set_provider,
)
from app.core.tenant_store import InMemoryTenantStore, TenantRecord

# Well-known Azure CLI ROPC client — used when ENTRA_API_CLIENT_ID is absent.
_FALLBACK_ROPC_CLIENT = "04b07795-8ddb-461a-bbee-02f9e1bf7b46"


# ---------------------------------------------------------------------------
# Token acquisition (ROPC — mirrors access_control_test.py, urllib only)
# ---------------------------------------------------------------------------

def _ropc_token(tid: str, upn: str, password: str, client_id: str) -> str:
    """Acquire an ROPC access token from Entra for the given tenant+user.

    Scope: api://<client_id>/access_as_user  (the backend API audience).
    Uses the same urllib pattern as access_control_test.py — no new deps.
    """
    scope = f"api://{client_id}/access_as_user"
    body = urllib.parse.urlencode({
        "grant_type": "password",
        "client_id": client_id,
        "scope": scope,
        "username": upn,
        "password": password,
    }).encode()
    url = f"https://login.microsoftonline.com/{tid}/oauth2/v2.0/token"
    req = urllib.request.Request(url, data=body)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)["access_token"]


def _decode_tid(token: str) -> str:
    """Decode the `tid` claim from a JWT without a crypto lib (no verification needed here —
    we already trust it arrived from Entra; the decode is just for feeding resolve_tenant)."""
    # JWT is header.payload.signature — payload is base64url-encoded JSON.
    payload_b64 = token.split(".")[1]
    # Add padding so b64decode works.
    padding = 4 - len(payload_b64) % 4
    payload_b64 += "=" * (padding % 4)
    import base64
    claims = json.loads(base64.urlsafe_b64decode(payload_b64))
    return claims["tid"]


def _decode_oid(token: str) -> str:
    """Decode the `oid` claim from the JWT payload (same approach as _decode_tid)."""
    payload_b64 = token.split(".")[1]
    padding = 4 - len(payload_b64) % 4
    payload_b64 += "=" * (padding % 4)
    import base64
    claims = json.loads(base64.urlsafe_b64decode(payload_b64))
    return claims["oid"]


# ---------------------------------------------------------------------------
# Gate: read env vars and decide whether to skip or run
# ---------------------------------------------------------------------------

def _required_config() -> dict | None:
    """Return the full config dict if ALL required vars are present, else None."""
    def _e(name: str) -> str:
        return os.environ.get(name, "").strip()

    deployment_mode = _e("DEPLOYMENT_MODE")
    a_tid = _e("TENANT_E2E_A_TID")
    a_user = _e("TENANT_E2E_A_USER")
    a_password = _e("TENANT_E2E_A_PASSWORD")
    a_oid = _e("TENANT_E2E_A_OID")
    b_tid = _e("TENANT_E2E_B_TID")
    b_user = _e("TENANT_E2E_B_USER")
    b_password = _e("TENANT_E2E_B_PASSWORD")
    b_oid = _e("TENANT_E2E_B_OID")

    if not all([
        deployment_mode == "shared",
        a_tid, a_user, a_password, a_oid,
        b_tid, b_user, b_password, b_oid,
    ]):
        return None

    # ENTRA_API_CLIENT_ID: prefer explicit, fall back to well-known public ROPC client.
    client_id = _e("ENTRA_API_CLIENT_ID") or _FALLBACK_ROPC_CLIENT

    return {
        "client_id": client_id,
        "a_tid": a_tid,
        "a_user": a_user,
        "a_password": a_password,
        "a_oid": a_oid,
        "b_tid": b_tid,
        "b_user": b_user,
        "b_password": b_password,
        "b_oid": b_oid,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_store(cfg: dict) -> InMemoryTenantStore:
    """Seed an InMemoryTenantStore with placeholder TenantConfigs for A and B.

    The data_plane values are intentionally distinct (different foundry_model)
    so we can verify each tenant sees its own config, not the other's.
    """
    store = InMemoryTenantStore()
    store.put(TenantRecord(
        tid=cfg["a_tid"], name="Tenant-A", tier="shared", status="active",
        data_plane=TenantConfig(foundry_model="gpt-5-mini-a"),
    ))
    store.put(TenantRecord(
        tid=cfg["b_tid"], name="Tenant-B", tier="shared", status="active",
        data_plane=TenantConfig(foundry_model="gpt-5-mini-b"),
    ))
    # Suspended entry for test (d).
    store.put(TenantRecord(
        tid="suspended-tid-e2e", name="Suspended", tier="shared", status="suspended",
        data_plane=TenantConfig(),
    ))
    return store


def _resolve_and_set(user_ns, store: InMemoryTenantStore) -> None:
    """Call resolve_tenant then MultiTenantConfigProvider.current() to set everything."""
    auth.resolve_tenant(user_ns, store)


def _assert_403(user_ns, store: InMemoryTenantStore) -> bool:
    set_current_tenant(None)
    try:
        auth.resolve_tenant(user_ns, store)
        return False
    except HTTPException as exc:
        return exc.status_code == 403


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    cfg = _required_config()
    if cfg is None:
        print(
            "– tenant E2E skipped "
            "(set DEPLOYMENT_MODE=shared + TENANT_E2E_A_*/TENANT_E2E_B_* creds to run)"
        )
        return 0

    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        mark = "✓" if cond else "✗"
        print(f"  {mark} {name}")
        if not cond:
            failures.append(name)

    print("tenant E2E — acquiring tokens …")

    # Acquire real tokens from Entra for the two test tenants.
    try:
        token_a = _ropc_token(cfg["a_tid"], cfg["a_user"], cfg["a_password"], cfg["client_id"])
        print(f"  token A acquired (tid={cfg['a_tid'][:8]}…)")
    except Exception as exc:  # noqa: BLE001
        print(f"  ✗ failed to acquire token for tenant A: {exc}")
        return 1

    try:
        token_b = _ropc_token(cfg["b_tid"], cfg["b_user"], cfg["b_password"], cfg["client_id"])
        print(f"  token B acquired (tid={cfg['b_tid'][:8]}…)")
    except Exception as exc:  # noqa: BLE001
        print(f"  ✗ failed to acquire token for tenant B: {exc}")
        return 1

    # Decode tid/oid from the real tokens (Entra-issued, trusted source).
    decoded_a_tid = _decode_tid(token_a)
    decoded_a_oid = _decode_oid(token_a)
    decoded_b_tid = _decode_tid(token_b)
    decoded_b_oid = _decode_oid(token_b)

    # The oid from the token is authoritative; the env var is used to cross-check.
    check("decoded tid A matches TENANT_E2E_A_TID", decoded_a_tid == cfg["a_tid"])
    check("decoded oid A matches TENANT_E2E_A_OID", decoded_a_oid == cfg["a_oid"])
    check("decoded tid B matches TENANT_E2E_B_TID", decoded_b_tid == cfg["b_tid"])
    check("decoded oid B matches TENANT_E2E_B_OID", decoded_b_oid == cfg["b_oid"])

    # Wire MultiTenantConfigProvider for this test run.
    set_provider(MultiTenantConfigProvider())

    store = _seed_store(cfg)

    print("\n  — test (a): tenant A resolution —")
    set_current_tenant(None)
    auth._current_user.set(None)
    user_a = SimpleNamespace(tid=decoded_a_tid, oid=decoded_a_oid)
    _resolve_and_set(user_a, store)

    check("(a) current_tenant_id == A's tid", current_tenant_id() == cfg["a_tid"])
    check("(a) tenant_config() returns A's data-plane (foundry_model)",
          _try_get_config("gpt-5-mini-a"))

    print("\n  — test (b): tenant B resolution —")
    set_current_tenant(None)
    auth._current_user.set(None)
    user_b = SimpleNamespace(tid=decoded_b_tid, oid=decoded_b_oid)
    _resolve_and_set(user_b, store)

    check("(b) current_tenant_id == B's tid", current_tenant_id() == cfg["b_tid"])
    check("(b) tenant_config() returns B's data-plane (foundry_model)",
          _try_get_config("gpt-5-mini-b"))
    check("(b) B's tid differs from A's tid", cfg["b_tid"] != cfg["a_tid"])

    print("\n  — test (c): unknown tid → 403 —")
    unknown_user = SimpleNamespace(tid="unknown-tid-that-is-not-onboarded", oid="any-oid")
    check("(c) unknown tid → 403", _assert_403(unknown_user, store))

    print("\n  — test (d): suspended tenant → 403 —")
    suspended_user = SimpleNamespace(tid="suspended-tid-e2e", oid="any-oid")
    check("(d) suspended tid → 403", _assert_403(suspended_user, store))

    print("\n  — test (e): memory_scope isolation —")
    # Resolve A again to set _current_tenant for memory_scope.
    set_current_tenant(None)
    _resolve_and_set(user_a, store)
    auth._current_user.set(SimpleNamespace(oid=decoded_a_oid, roles=[]))
    scope_a = auth.memory_scope()
    expected_scope_a = f"{cfg['a_tid']}:{decoded_a_oid}"
    check("(e) memory_scope for A is tid:oid", scope_a == expected_scope_a)

    set_current_tenant(None)
    _resolve_and_set(user_b, store)
    auth._current_user.set(SimpleNamespace(oid=decoded_b_oid, roles=[]))
    scope_b = auth.memory_scope()
    expected_scope_b = f"{cfg['b_tid']}:{decoded_b_oid}"
    check("(e) memory_scope for B is tid:oid", scope_b == expected_scope_b)
    check("(e) A and B memory scopes are different", scope_a != scope_b)
    check("(e) scope A has A's tid prefix", scope_a.startswith(cfg["a_tid"] + ":"))
    check("(e) scope B has B's tid prefix", scope_b.startswith(cfg["b_tid"] + ":"))

    print("\n  — test (f): _iss_callable issuer format —")
    from app.core.auth import _iss_callable
    iss_a = _iss_callable(cfg["a_tid"])
    iss_b = _iss_callable(cfg["b_tid"])
    check("(f) issuer A is per-tenant v2 endpoint",
          iss_a == f"https://login.microsoftonline.com/{cfg['a_tid']}/v2.0")
    check("(f) issuer B is per-tenant v2 endpoint",
          iss_b == f"https://login.microsoftonline.com/{cfg['b_tid']}/v2.0")
    check("(f) issuers A and B differ", iss_a != iss_b)

    # Clean up contextvars for safety.
    set_current_tenant(None)
    auth._current_user.set(None)

    print()
    if failures:
        print(f"❌ {len(failures)} assertion(s) failed: {failures}")
        return 1
    print("✅ tenant E2E — per-tenant isolation holds (a)–(f) all green.")
    return 0


def _try_get_config(expected_model: str) -> bool:
    """Check that tenant_config().foundry_model matches expected_model, returning bool."""
    from app.core.tenant import tenant_config
    try:
        cfg = tenant_config()
        return cfg.foundry_model == expected_model
    except RuntimeError:
        return False


if __name__ == "__main__":
    sys.exit(main())
