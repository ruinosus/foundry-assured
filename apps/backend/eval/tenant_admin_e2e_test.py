"""Sub-project B infra-gated E2E proof — onboard → config → connection-CRUD + deny path.

Exercises the LIVE TableStorageTenantStore (Azure Table Storage) plus the
onboarding_guard logic, with_connection / without_connection helpers, and the deny
path via a non-allow-listed tid.  The infra-gated value is TRUE PERSISTENCE: the
TenantRecord travels to Azure Table Storage and comes back correctly through a fresh
store.get() call.

When the required environment is absent the module SKIPS CLEANLY (prints a skip note,
exits 0), so an offline eval sweep stays green.

== What the test proves ==
  (a) onboard: allow-listed Admin creates a TenantRecord in TableStorageTenantStore;
      store.get() returns it with status "active".
  (b) config update: PUT /config equivalent (read-modify-write) persists the new
      data_plane fields through a fresh store.get().
  (c) connection add (with_connection): a github Connection is upserted; store.get()
      includes it.
  (d) connection list: the connection appears in store.get().connections.
  (e) connection remove (without_connection): the connection is removed; store.get()
      has an empty connections tuple.
  (f) deny: onboarding_guard rejects a caller whose tid is NOT in allowed_tids, raising
      HTTPException(403).

== Required environment variables ==
ALL of the following must be set for the real assertions to run.
Set them in a .env file or CI secrets — never commit them.

  # Deployment mode gate
  DEPLOYMENT_MODE=shared

  # Live Table Storage (the control-plane store)
  TENANT_STORE_ACCOUNT_URL   Azure Storage account URL, e.g.
                             https://<account>.table.core.windows.net

  # Test tenant identity (reused from the A E2E's naming convention)
  # These identify the Entra tenant and a test user that will be treated as the
  # onboarding caller. Token acquisition is OPTIONAL for this test (we exercise
  # the store + guard directly), but the tid/oid are needed to populate the
  # SimpleNamespace user that feeds onboarding_guard.
  TENANT_E2E_A_TID        Tenant ID (GUID) that will be allow-listed for onboarding.
  TENANT_E2E_A_OID        Object ID (GUID) of the test user in that tenant.
                          (Used as a label only; not verified against Entra here.)

  # Platform allow-list — the test patches settings.onboarding_allowed_tids to include
  # TENANT_E2E_A_TID, so no .env change is needed at the platform level.

  (Optional — if you also want a real Entra token for additional coverage)
  TENANT_E2E_A_USER       UPN (email) of the ROPC test user.
  TENANT_E2E_A_PASSWORD   Password of that test user.
  ENTRA_API_CLIENT_ID     Client ID of the backend API app registration.

== Run ==
  uv run python -m eval.tenant_admin_e2e_test

Skip note is printed when infra is absent; exit 0 either way.
"""

from __future__ import annotations

import os
import sys
import uuid
from types import SimpleNamespace

from fastapi import HTTPException


# ---------------------------------------------------------------------------
# Gate: read env vars and decide whether to skip or run
# ---------------------------------------------------------------------------

def _required_config() -> dict | None:
    """Return config dict if ALL required vars are present, else None."""

    def _e(name: str) -> str:
        return os.environ.get(name, "").strip()

    deployment_mode = _e("DEPLOYMENT_MODE")
    account_url = _e("TENANT_STORE_ACCOUNT_URL")
    a_tid = _e("TENANT_E2E_A_TID")
    a_oid = _e("TENANT_E2E_A_OID")

    if not all([
        deployment_mode == "shared",
        account_url,
        a_tid,
        a_oid,
    ]):
        return None

    return {
        "account_url": account_url,
        "a_tid": a_tid,
        "a_oid": a_oid,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    cfg = _required_config()
    if cfg is None:
        print(
            "– tenant-admin E2E skipped "
            "(set DEPLOYMENT_MODE=shared + TENANT_STORE_ACCOUNT_URL to run)"
        )
        return 0

    # Import here (after the gate) so offline runs never import azure-data-tables.
    from azure.identity import DefaultAzureCredential

    from app.core.settings import settings
    from app.core.tenant import TenantConfig
    from app.core.tenant_store import (
        Connection,
        TableStorageTenantStore,
        TenantRecord,
        with_connection,
        without_connection,
    )
    from app.core.onboarding import onboarding_guard

    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        mark = "✓" if cond else "✗"
        print(f"  {mark} {name}")
        if not cond:
            failures.append(name)

    # Use a unique test-run suffix so parallel CI runs don't collide on the same row.
    run_id = uuid.uuid4().hex[:8]
    test_tid = f"{cfg['a_tid']}"          # the real Entra tid (used as PartitionKey)
    test_table = f"e2etenantadmin{run_id}"  # isolated table per run, cleaned up at the end

    print(f"tenant-admin E2E — table={test_table}, tid={test_tid[:8]}…")

    # Build the live store.
    credential = DefaultAzureCredential()
    store = TableStorageTenantStore(
        account_url=cfg["account_url"],
        table_name=test_table,
        credential=credential,
    )

    # Patch the platform allow-list to include our test tid.
    original_allowed = settings.onboarding_allowed_tids
    settings.onboarding_allowed_tids = cfg["a_tid"]

    try:
        # ------------------------------------------------------------------ #
        # (a) onboard: allow-listed Admin creates a TenantRecord             #
        # ------------------------------------------------------------------ #
        print("\n  — (a) onboard —")

        # Simulate what POST /onboard does after onboarding_guard passes.
        # onboarding_guard checks user.roles for "Admin" and user.tid against allowed_tids.
        admin_user = SimpleNamespace(
            tid=cfg["a_tid"], oid=cfg["a_oid"], roles=["Admin"],
        )
        # Call the guard directly (no running HTTP server needed).
        guard_returned_user = onboarding_guard(user=admin_user)  # type: ignore[arg-type]
        check("(a) onboarding_guard returns the user for an allow-listed Admin",
              guard_returned_user is admin_user)

        # Write the record (mirrors POST /onboard handler body).
        if store.get(test_tid) is None:
            store.put(TenantRecord(
                tid=test_tid, name=test_tid, tier="shared", status="active",
                data_plane=TenantConfig(),
            ))

        rec = store.get(test_tid)
        check("(a) record exists after onboard", rec is not None)
        check("(a) status is active", rec is not None and rec.status == "active")
        check("(a) tier is shared", rec is not None and rec.tier == "shared")

        # ------------------------------------------------------------------ #
        # (b) config update: persists the new data_plane through store.get() #
        # ------------------------------------------------------------------ #
        print("\n  — (b) config update —")

        rec = store.get(test_tid)
        assert rec is not None  # guaranteed by (a)

        from dataclasses import replace
        new_data_plane = replace(
            rec.data_plane,
            foundry_project_endpoint="https://e2e-test.api.azureml.ms",
            foundry_model="gpt-5-mini",
        )
        store.put(replace(rec, data_plane=new_data_plane))

        rec2 = store.get(test_tid)
        check("(b) foundry_project_endpoint persisted",
              rec2 is not None and rec2.data_plane.foundry_project_endpoint == "https://e2e-test.api.azureml.ms")
        check("(b) foundry_model persisted",
              rec2 is not None and rec2.data_plane.foundry_model == "gpt-5-mini")

        # ------------------------------------------------------------------ #
        # (c) connection add via with_connection                             #
        # ------------------------------------------------------------------ #
        print("\n  — (c) connection add —")

        rec2 = store.get(test_tid)
        assert rec2 is not None

        conn = Connection(
            id="gh-main",
            kind="github",
            label="GitHub main org",
            foundry_connection_id="fconn-e2e-test-001",
        )
        store.put(with_connection(rec2, conn))

        rec3 = store.get(test_tid)
        check("(c) connection persisted", rec3 is not None and len(rec3.connections) == 1)
        if rec3 and rec3.connections:
            c = rec3.connections[0]
            check("(c) connection id matches", c.id == "gh-main")
            check("(c) connection kind matches", c.kind == "github")
            check("(c) foundry_connection_id matches", c.foundry_connection_id == "fconn-e2e-test-001")
        else:
            failures.extend(["(c) connection id matches", "(c) connection kind matches",
                              "(c) foundry_connection_id matches"])

        # ------------------------------------------------------------------ #
        # (d) connection list: verify it appears                             #
        # ------------------------------------------------------------------ #
        print("\n  — (d) connection list —")

        rec3 = store.get(test_tid)
        conn_ids = [c.id for c in rec3.connections] if rec3 else []
        check("(d) gh-main appears in connections", "gh-main" in conn_ids)

        # ------------------------------------------------------------------ #
        # (e) connection remove via without_connection                       #
        # ------------------------------------------------------------------ #
        print("\n  — (e) connection remove —")

        rec3 = store.get(test_tid)
        assert rec3 is not None

        store.put(without_connection(rec3, "gh-main"))

        rec4 = store.get(test_tid)
        check("(e) connection removed from store",
              rec4 is not None and len(rec4.connections) == 0)

        # ------------------------------------------------------------------ #
        # (f) deny: non-allow-listed tid → onboarding_guard raises 403       #
        # ------------------------------------------------------------------ #
        print("\n  — (f) deny path —")

        non_allowed_user = SimpleNamespace(
            tid="non-allow-listed-tid-e2e-test", oid="any-oid", roles=["Admin"],
        )
        raised_403 = False
        try:
            onboarding_guard(user=non_allowed_user)  # type: ignore[arg-type]
        except HTTPException as exc:
            raised_403 = exc.status_code == 403
        check("(f) non-allow-listed Admin tid → 403", raised_403)

    finally:
        # Restore the original allow-list.
        settings.onboarding_allowed_tids = original_allowed

        # Clean up the test table (best-effort).
        try:
            from azure.data.tables import TableServiceClient
            svc = TableServiceClient(endpoint=cfg["account_url"], credential=credential)
            svc.delete_table(test_table)
            print(f"\n  (cleanup: deleted table {test_table})")
        except Exception as cleanup_exc:  # noqa: BLE001
            print(f"\n  (cleanup: could not delete table {test_table}: {cleanup_exc})")

    print()
    if failures:
        print(f"❌ {len(failures)} assertion(s) failed: {failures}")
        return 1
    print("✅ tenant-admin E2E — onboard → config → connection-CRUD + deny all green (a)–(f).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
