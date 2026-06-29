# Sub-project A — Multi-tenant Foundation Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce the `TenantConfigProvider` + `DEPLOYMENT_MODE` seam so the same codebase runs single-tenant (self-hosted, today) or multi-tenant (shared SaaS) — shipped SingleTenant-first with **zero behavior change**, then MultiTenant behind a swappable `TenantStore`.

**Architecture:** Split the global `settings` into `PlatformSettings` (global) + `TenantConfig` (per-tenant, resolved by a provider chosen at boot by `DEPLOYMENT_MODE`). `SingleTenant` builds `TenantConfig` from `.env` (= today). `MultiTenant` resolves it by the token's `tid` from a `TenantStore` (Azure Table Storage first), gated in `require_user` which is the single tenant-scoping choke point. `memory_scope` stays un-prefixed single-tenant, `tid`-prefixed multi-tenant.

**Tech Stack:** Python 3.12, `pydantic-settings`, `fastapi_azure_auth` (Single/Multi-tenant bearer schemes — both confirmed installed), `azure-data-tables` (NEW dependency), `azure-identity` (`DefaultAzureCredential`), `contextvars`.

**Spec:** [`2026-06-29-subproject-a-multitenant-foundation-design.md`](../specs/2026-06-29-subproject-a-multitenant-foundation-design.md) — read it first.

**Testing convention (IMPORTANT — not pytest):** tests are runnable modules under `apps/backend/eval/`, shaped `def main() -> int:` (print `✓`/`✗`, non-zero on failure) + `if __name__ == "__main__": sys.exit(main())`, run via `uv run python -m eval.<name>`. Template: `eval/test_attribution.py`. All backend commands run from `apps/backend/`.

---

## File Structure

**Backend (create):**
- `apps/backend/app/core/tenant.py` — `TenantConfig` (frozen dataclass), `_TenantEnv` (per-tenant env loader for SingleTenant), `TenantConfigProvider` protocol + `SingleTenantConfigProvider` + `MultiTenantConfigProvider`, the `_current_tenant` contextvar, and the module accessors `tenant_config()` / `current_tenant_id()` / `set_current_tenant()`. *One responsibility: resolve the current request's tenant config.*
- `apps/backend/app/core/tenant_store.py` — `TenantRecord` (dataclass), `TenantStore` protocol, `InMemoryTenantStore` (tests), `TableStorageTenantStore`. *One responsibility: persist/fetch per-tenant records by `tid`.*
- `apps/backend/eval/tenant_provider_test.py`, `eval/tenant_store_test.py`, `eval/memory_scope_test.py`, `eval/tenant_resolution_test.py` — runnable unit tests.
- `apps/backend/eval/tenant_e2e_test.py` — infra-gated second-tenant E2E (Chunk 3).

**Backend (modify):**
- `apps/backend/app/core/settings.py` — `Settings` → `PlatformSettings` (global fields only) + the new `deployment_mode` / `tenant_store_table`; the per-tenant fields move conceptually to `TenantConfig` (kept readable from env by `_TenantEnv`).
- `apps/backend/app/core/auth.py` — scheme selection by mode (preserving the auth-off no-op), `require_user` tenant resolution, the `memory_scope` guard.
- The per-tenant `settings.<field>` call sites (agents, workflow, secure_search, knowledge) → `tenant_config().<field>`.
- `apps/backend/pyproject.toml` — add `azure-data-tables`.

---

## Chunk 1: Step 1 — the provider seam, SingleTenant only (ZERO behavior change)

No multi-tenancy yet. `current_tenant_id()` always returns `None`; `memory_scope` stays bare. The gate for this chunk is **the existing eval suite stays green** — identical runtime behavior.

### Task 1: `TenantConfig` + provider + SingleTenant impl

**Files:**
- Create: `apps/backend/app/core/tenant.py`
- Test: `apps/backend/eval/tenant_provider_test.py`

- [ ] **Step 1: Write the failing test**

Create `apps/backend/eval/tenant_provider_test.py`:

```python
"""Unit test for the tenant-config seam (infra-free).

SingleTenant returns the .env-built config (= today's values); current_tenant_id() is None
in single-tenant mode so memory_scope stays bare.

    uv run python -m eval.tenant_provider_test
"""

from __future__ import annotations

import os
import sys

from app.core.tenant import (
    SingleTenantConfigProvider,
    TenantConfig,
    current_tenant_id,
)


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {name}")
        if not cond:
            failures.append(name)

    os.environ["FOUNDRY_MODEL"] = "gpt-5-mini"
    cfg = SingleTenantConfigProvider().current()
    check("SingleTenant returns a TenantConfig", isinstance(cfg, TenantConfig))
    check("reads FOUNDRY_MODEL from env", cfg.foundry_model == "gpt-5-mini")
    check("current_tenant_id() is None in single-tenant mode", current_tenant_id() is None)

    if failures:
        print(f"\n❌ {len(failures)} assertion(s) failed.")
        return 1
    print("\n✅ tenant provider (SingleTenant) holds.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run python -m eval.tenant_provider_test`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.tenant'`.

- [ ] **Step 3: Write `tenant.py`**

Create `apps/backend/app/core/tenant.py`:

```python
"""Per-tenant config resolution — the one seam that varies by DEPLOYMENT_MODE.

SingleTenant (self_hosted/dedicated) builds TenantConfig from .env = today's behavior.
MultiTenant (shared) resolves it from the per-request tenant set in require_user. The core
(agents, workflow) only ever calls tenant_config(); it never knows the mode.
"""

from __future__ import annotations

import contextvars
from dataclasses import dataclass
from typing import Protocol

from pydantic_settings import BaseSettings, SettingsConfigDict


@dataclass(frozen=True)
class TenantConfig:
    """Per-tenant data-plane pointers (customer resources). ZERO secrets.

    Illustrative subset; the file-split task adds the rest (storage, embedding, per-domain
    KBs, ACL, memory store, hosted agent) per the spec's field classification.
    """
    foundry_project_endpoint: str = ""
    foundry_model: str = "gpt-5-mini"
    azure_search_endpoint: str = ""
    azure_search_knowledge_base: str = "helpdesk-kb"


class _TenantEnv(BaseSettings):
    """Loads the per-tenant fields from .env (same env var names as today) for SingleTenant."""
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    foundry_project_endpoint: str = ""
    foundry_model: str = "gpt-5-mini"
    azure_search_endpoint: str = ""
    azure_search_knowledge_base: str = "helpdesk-kb"

    def as_config(self) -> TenantConfig:
        return TenantConfig(
            foundry_project_endpoint=self.foundry_project_endpoint,
            foundry_model=self.foundry_model,
            azure_search_endpoint=self.azure_search_endpoint,
            azure_search_knowledge_base=self.azure_search_knowledge_base,
        )


class TenantConfigProvider(Protocol):
    def current(self) -> TenantConfig: ...


class SingleTenantConfigProvider:
    """self_hosted / dedicated — one config from .env. Identical to today."""

    def current(self) -> TenantConfig:
        return _TenantEnv().as_config()


# The per-request resolved tenant record (set by require_user in multi-tenant mode).
# Holds Any to avoid importing tenant_store here (tenant_store imports TenantConfig from us).
_current_tenant: contextvars.ContextVar[object | None] = contextvars.ContextVar(
    "current_tenant", default=None
)


def set_current_tenant(record: object | None) -> None:
    _current_tenant.set(record)


def current_tenant_id() -> str | None:
    """The resolved tenant's tid, or None outside shared mode (used by memory_scope)."""
    rec = _current_tenant.get()
    return getattr(rec, "tid", None) if rec is not None else None


# The active provider, selected at boot (Task 6 wires DEPLOYMENT_MODE; default = SingleTenant).
_provider: TenantConfigProvider = SingleTenantConfigProvider()


def set_provider(provider: TenantConfigProvider) -> None:
    global _provider
    _provider = provider


def tenant_config() -> TenantConfig:
    """The current request's tenant config. The accessor every per-tenant call site uses."""
    return _provider.current()
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run python -m eval.tenant_provider_test`
Expected: PASS — `✅ tenant provider (SingleTenant) holds.`

- [ ] **Step 5: Commit**

```bash
git add apps/backend/app/core/tenant.py apps/backend/eval/tenant_provider_test.py
git commit -m "feat(tenant): TenantConfigProvider seam + SingleTenant impl (zero behavior change)"
```

### Task 2: Split `settings.py` into `PlatformSettings`; route per-tenant reads through `tenant_config()`

**Files:**
- Modify: `apps/backend/app/core/settings.py`
- Modify: the per-tenant call sites (see Step 3)

- [ ] **Step 1: Reduce `settings.py` to platform-global fields**

In `apps/backend/app/core/settings.py`, rename `Settings` → `PlatformSettings`, **keep only the
global fields** (per the spec's classification): `deployment_mode` (new, default `"self_hosted"`),
`tenant_store_table` (new, default `"tenants"`), `tenant_store_account_url` (new, default `""` —
the **control-plane** Storage account's Table endpoint, e.g.
`https://<acct>.table.core.windows.net`; platform-global because the store is built at boot
*before* any tenant is resolved, so it CANNOT come from per-tenant `tenant_config()`),
`frontend_origin`, `entra_tenant_id`,
`entra_api_client_id`, `entra_api_client_secret`, `entra_spa_client_id`, and the derived
properties `auth_enabled` + `entra_api_scope`. Keep the module-level instance named `settings`
(so platform call sites are unchanged): `settings = PlatformSettings()`. Remove the per-tenant
fields (they now live in `TenantConfig` / `_TenantEnv`).

> Do this incrementally: the moment a per-tenant field is removed from `PlatformSettings`, every
> `settings.<that field>` reference is a NameError until migrated in Step 3. Migrate in the same
> commit so the app boots.

- [ ] **Step 2: Find every per-tenant call site**

Run: `cd apps/backend && grep -rn "settings\.\(foundry_project_endpoint\|foundry_model\|azure_search_endpoint\|azure_search_knowledge_base\|azure_storage\|foundry_embedding_model\|azure_ai_openai_endpoint\|foundry_memory_store\|hosted_agent_name\|cockpit_\|selfwiki_\|acl_group_map\)" app/`
Expected: a list across `app/agents/*`, `app/workflow/*`, `app/knowledge/*`, `app/services/*`, `app/api/*`. These are the sites to migrate.

- [ ] **Step 3: Migrate each per-tenant read to `tenant_config()`**

For each hit, add `from app.core.tenant import tenant_config` and replace
`settings.foundry_model` → `tenant_config().foundry_model`, etc. **Extend `TenantConfig` /
`_TenantEnv`** in `tenant.py` to carry every per-tenant field you migrate (storage, embedding,
per-domain KBs, ACL, memory store, hosted agent) — keep the dataclass and the env loader in sync
(same field names, same defaults as today). Platform reads (`settings.frontend_origin`,
`settings.entra_*`) stay as-is.

> Keep behavior identical: `_TenantEnv` reads the **same env var names** with the **same
> defaults** the old `Settings` had, so a self-hosted deploy reads exactly what it read before.

> ⚠️ **Module-level reads — do NOT mechanically replace.** Two sites read a per-tenant field at
> **import time**, not per-request: `app/agents/secure_search.py:36` and
> `app/knowledge/acl_setup.py:34` (both `_INDEX = settings.cockpit_search_index`).
> `tenant_config()` at import works in SingleTenant but **crashes boot in `shared` mode**
> (`MultiTenantConfigProvider.current()` with no `_current_tenant` → `RuntimeError`). **Convert
> these to lazy per-call lookups:** delete the `_INDEX = …` module constant and read
> `tenant_config().cockpit_search_index` **inside the function bodies** that use it (e.g.
> `secure_search.py:57`). Before migrating, sweep for any other module-level per-tenant constant:
> `grep -rnE "^_?[A-Z][A-Za-z_]* *= *.*settings\." app/` — every hit must become a per-call read,
> not an import-time one.

- [ ] **Step 4: Boot + the zero-behavior-change gate (existing evals green)**

Run: `MCP_ENABLED=0 uv run python -c "import app.main"` → boots without NameError.
Then run the existing eval suite that doesn't need new infra, e.g.:
`uv run python -m eval.test_attribution` and `uv run python -m eval.tenant_provider_test`
Expected: PASS — behavior unchanged. *(If any eval needs live infra, run the infra-free ones; the guarantee is "no behavior change," proven by green evals + a clean boot.)*

- [ ] **Step 5: Commit**

```bash
git add apps/backend/app/core/settings.py apps/backend/app/core/tenant.py apps/backend/app/
git commit -m "refactor(tenant): split PlatformSettings; route per-tenant reads through tenant_config() (no behavior change)"
```

### Task 3: `memory_scope` guard (inert in single-tenant)

**Files:**
- Modify: `apps/backend/app/core/auth.py`
- Test: `apps/backend/eval/memory_scope_test.py`

- [ ] **Step 1: Write the failing test**

Create `apps/backend/eval/memory_scope_test.py`:

```python
"""memory_scope: bare in single-tenant (no orphaned memories), tid-prefixed in multi-tenant.

Drives the two contextvars directly — no store, no network.

    uv run python -m eval.memory_scope_test
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

from app.core import auth
from app.core.tenant import set_current_tenant


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {name}")
        if not cond:
            failures.append(name)

    # Single-tenant: a user, no tenant set → bare oid (today's behavior).
    auth._current_user.set(SimpleNamespace(oid="user-123", roles=[]))
    set_current_tenant(None)
    check("single-tenant scope is bare oid", auth.memory_scope() == "user-123")

    # Multi-tenant: a resolved tenant with a tid → prefixed.
    set_current_tenant(SimpleNamespace(tid="tenant-abc"))
    check("multi-tenant scope is tid:oid", auth.memory_scope() == "tenant-abc:user-123")

    # No user at all → dev-local (auth-off path), still works.
    auth._current_user.set(None)
    set_current_tenant(None)
    check("no user → dev-local", auth.memory_scope() == "dev-local")

    set_current_tenant(None)
    if failures:
        print(f"\n❌ {len(failures)} assertion(s) failed.")
        return 1
    print("\n✅ memory_scope guard holds.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run python -m eval.memory_scope_test`
Expected: FAIL — multi-tenant case returns `user-123` (no prefix yet).

- [ ] **Step 3: Add the guard to `memory_scope`**

In `apps/backend/app/core/auth.py`, update `memory_scope` to:

```python
def memory_scope() -> str:
    """Per-user memory namespace, tenant-prefixed in multi-tenant mode.

    SingleTenant keeps the bare user.oid (memory keys are persisted — prefixing would orphan
    existing memories). Only MultiTenant prefixes by tid.
    """
    from app.core.tenant import current_tenant_id  # local import avoids a cycle
    user = current_user()
    base = user.oid if (user is not None and user.oid) else "dev-local"
    tid = current_tenant_id()
    return f"{tid}:{base}" if tid else base
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run python -m eval.memory_scope_test`
Expected: PASS — `✅ memory_scope guard holds.`

- [ ] **Step 5: Commit**

```bash
git add apps/backend/app/core/auth.py apps/backend/eval/memory_scope_test.py
git commit -m "feat(tenant): memory_scope guard (bare single-tenant, tid-prefixed multi-tenant)"
```

---

## Chunk 2: Step 2 — multi-tenancy (off by default, `DEPLOYMENT_MODE=shared`)

### Task 4: `TenantStore` + in-memory fake + Table Storage impl

**Files:**
- Create: `apps/backend/app/core/tenant_store.py`
- Modify: `apps/backend/pyproject.toml` (add `azure-data-tables`)
- Test: `apps/backend/eval/tenant_store_test.py`

- [ ] **Step 1: Add the dependency**

Run: `cd apps/backend && uv add azure-data-tables`
Expected: `azure-data-tables` added to `pyproject.toml` + lockfile.

- [ ] **Step 2: Write the failing test**

Create `apps/backend/eval/tenant_store_test.py`:

```python
"""TenantStore round-trip via the in-memory fake (infra-free). Table Storage shares the
same interface and is exercised in the Chunk 3 E2E.

    uv run python -m eval.tenant_store_test
"""

from __future__ import annotations

import sys

from app.core.tenant import TenantConfig
from app.core.tenant_store import InMemoryTenantStore, TenantRecord


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {name}")
        if not cond:
            failures.append(name)

    store = InMemoryTenantStore()
    rec = TenantRecord(
        tid="tenant-abc", name="Acme", tier="shared", status="active",
        data_plane=TenantConfig(foundry_model="gpt-5-mini"),
    )
    store.put(rec)
    check("get returns the stored record", store.get("tenant-abc") == rec)
    check("unknown tid → None (deny path)", store.get("nope") is None)
    check("list includes it", rec in store.list())

    if failures:
        print(f"\n❌ {len(failures)} assertion(s) failed.")
        return 1
    print("\n✅ tenant store (in-memory) holds.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Run to verify it fails**

Run: `uv run python -m eval.tenant_store_test`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.tenant_store'`.

- [ ] **Step 4: Write `tenant_store.py`**

Create `apps/backend/app/core/tenant_store.py`:

```python
"""Per-tenant record persistence, keyed by tid. Swappable: the InMemory fake is for tests,
TableStorage is the first real impl (cheapest — reuses the existing Storage account). Swap to
Cosmos/Postgres later = another class implementing TenantStore.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from typing import Protocol

from app.core.tenant import TenantConfig


@dataclass(frozen=True)
class TenantRecord:
    tid: str
    name: str
    tier: str            # shared | dedicated | self_hosted
    status: str          # active | suspended
    data_plane: TenantConfig


class TenantStore(Protocol):
    def get(self, tid: str) -> TenantRecord | None: ...
    def put(self, rec: TenantRecord) -> None: ...
    def list(self) -> list[TenantRecord]: ...


class InMemoryTenantStore:
    """Test/dev fake."""

    def __init__(self) -> None:
        self._by_tid: dict[str, TenantRecord] = {}

    def get(self, tid: str) -> TenantRecord | None:
        return self._by_tid.get(tid)

    def put(self, rec: TenantRecord) -> None:
        self._by_tid[rec.tid] = rec

    def list(self) -> list[TenantRecord]:
        return list(self._by_tid.values())


class TableStorageTenantStore:
    """Azure Table Storage (keyless) on the existing Storage account. PartitionKey=tid,
    RowKey='config'. data_plane is stored as a JSON property (Table props are flat/scalar).
    """

    def __init__(self, account_url: str, table_name: str, credential) -> None:
        from azure.data.tables import TableServiceClient  # lazy: only the shared mode needs it
        svc = TableServiceClient(endpoint=account_url, credential=credential)
        self._table = svc.create_table_if_not_exists(table_name)

    def get(self, tid: str) -> TenantRecord | None:
        from azure.core.exceptions import ResourceNotFoundError
        try:
            e = self._table.get_entity(partition_key=tid, row_key="config")
        except ResourceNotFoundError:
            return None
        return TenantRecord(
            tid=tid, name=e["name"], tier=e["tier"], status=e["status"],
            data_plane=TenantConfig(**json.loads(e["data_plane"])),
        )

    def put(self, rec: TenantRecord) -> None:
        self._table.upsert_entity({
            "PartitionKey": rec.tid, "RowKey": "config",
            "name": rec.name, "tier": rec.tier, "status": rec.status,
            "data_plane": json.dumps(asdict(rec.data_plane)),
        })

    def list(self) -> list[TenantRecord]:
        out: list[TenantRecord] = []
        for e in self._table.list_entities():
            out.append(TenantRecord(
                tid=e["PartitionKey"], name=e["name"], tier=e["tier"], status=e["status"],
                data_plane=TenantConfig(**json.loads(e["data_plane"])),
            ))
        return out
```

- [ ] **Step 5: Run to verify it passes**

Run: `uv run python -m eval.tenant_store_test`
Expected: PASS — `✅ tenant store (in-memory) holds.`

- [ ] **Step 6: Commit**

```bash
git add apps/backend/app/core/tenant_store.py apps/backend/eval/tenant_store_test.py apps/backend/pyproject.toml apps/backend/uv.lock
git commit -m "feat(tenant): TenantStore (in-memory fake + Table Storage impl)"
```

### Task 5: `MultiTenantConfigProvider`

**Files:**
- Modify: `apps/backend/app/core/tenant.py`
- Test: extend `apps/backend/eval/tenant_provider_test.py`

- [ ] **Step 1: Add the failing assertion** — append to `eval/tenant_provider_test.py`'s `main()` before the summary:

```python
    from app.core.tenant import MultiTenantConfigProvider, set_current_tenant
    from app.core.tenant_store import TenantRecord
    from types import SimpleNamespace
    rec = TenantRecord(tid="t1", name="n", tier="shared", status="active",
                       data_plane=TenantConfig(foundry_model="model-x"))
    set_current_tenant(rec)
    check("MultiTenant returns the resolved tenant's config",
          MultiTenantConfigProvider().current().foundry_model == "model-x")
    set_current_tenant(None)
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run python -m eval.tenant_provider_test`
Expected: FAIL — `ImportError: cannot import name 'MultiTenantConfigProvider'`.

- [ ] **Step 3: Add `MultiTenantConfigProvider` to `tenant.py`**

```python
class MultiTenantConfigProvider:
    """shared — the config of the tenant resolved for THIS request (set in require_user)."""

    def current(self) -> TenantConfig:
        rec = _current_tenant.get()
        if rec is None:
            raise RuntimeError("no tenant resolved for this request")
        return rec.data_plane  # type: ignore[attr-defined]
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run python -m eval.tenant_provider_test`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/backend/app/core/tenant.py apps/backend/eval/tenant_provider_test.py
git commit -m "feat(tenant): MultiTenantConfigProvider (reads the per-request tenant)"
```

### Task 6: Scheme selection by mode + `require_user` tenant resolution + deny path

**Files:**
- Modify: `apps/backend/app/core/auth.py`
- Test: `apps/backend/eval/tenant_resolution_test.py`

- [ ] **Step 1: Write the failing test** (the deny path + resolution, with a fake store)

Create `apps/backend/eval/tenant_resolution_test.py`:

```python
"""resolve_tenant: onboarded tid → sets _current_tenant; unknown/suspended → 403.

Exercises the authorization step in isolation with an in-memory store (no Entra, no network).

    uv run python -m eval.tenant_resolution_test
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

from fastapi import HTTPException

from app.core import auth
from app.core.tenant import TenantConfig, current_tenant_id, set_current_tenant
from app.core.tenant_store import InMemoryTenantStore, TenantRecord


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {name}")
        if not cond:
            failures.append(name)

    store = InMemoryTenantStore()
    store.put(TenantRecord(tid="t-ok", name="n", tier="shared", status="active",
                           data_plane=TenantConfig()))
    store.put(TenantRecord(tid="t-susp", name="n", tier="shared", status="suspended",
                           data_plane=TenantConfig()))

    set_current_tenant(None)
    auth.resolve_tenant(SimpleNamespace(tid="t-ok"), store)
    check("onboarded tid resolves", current_tenant_id() == "t-ok")

    def denies(tid: str) -> bool:
        set_current_tenant(None)
        try:
            auth.resolve_tenant(SimpleNamespace(tid=tid), store)
            return False
        except HTTPException as e:
            return e.status_code == 403

    check("unknown tid → 403", denies("t-unknown"))
    check("suspended tid → 403", denies("t-susp"))

    set_current_tenant(None)
    if failures:
        print(f"\n❌ {len(failures)} assertion(s) failed.")
        return 1
    print("\n✅ tenant resolution + deny path holds.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run python -m eval.tenant_resolution_test`
Expected: FAIL — `AttributeError: module 'app.core.auth' has no attribute 'resolve_tenant'`.

- [ ] **Step 3: Implement scheme selection + `resolve_tenant`, preserving the auth-off no-op**

In `apps/backend/app/core/auth.py`:

(a) Replace the scheme construction with mode-aware selection that **keeps the auth-off branch**:

```python
azure_scheme = None
if settings.auth_enabled:
    if settings.deployment_mode in ("self_hosted", "dedicated"):
        azure_scheme = SingleTenantAzureAuthorizationCodeBearer(
            app_client_id=settings.entra_api_client_id,
            tenant_id=settings.entra_tenant_id,
            scopes={settings.entra_api_scope: "access_as_user"},
            allow_guest_users=True,
        )
    else:  # shared
        azure_scheme = MultiTenantAzureAuthorizationCodeBearer(
            app_client_id=settings.entra_api_client_id,
            scopes={settings.entra_api_scope: "access_as_user"},
            validate_iss=True,
            # TODO (close condition): check the installed fastapi_azure_auth's
            # MultiTenantAzureAuthorizationCodeBearer — does validate_iss=True validate the
            # per-tenant issuer on its own, or is an iss_callable(tid)->issuer required? Inspect
            # `inspect.signature(MultiTenantAzureAuthorizationCodeBearer.__init__)` + the lib's
            # multitenant example. If a callable is required, pass one returning
            # f"https://login.microsoftonline.com/{tid}/v2.0". Done when the Chunk 3 (d) iss-
            # mismatch case rejects. (Rule: don't invent SDK signatures — verify, don't guess.)
            allow_guest_users=True,
        )
```

(Add `MultiTenantAzureAuthorizationCodeBearer` to the `fastapi_azure_auth` import.)

(b) Add `resolve_tenant` (the authorization step) and a module-level store:

```python
def _make_tenant_store():
    """Build the shared-mode store at boot. Uses the PLATFORM-global control-plane Storage
    account (settings.tenant_store_account_url) — NOT a per-tenant field, since no tenant is
    resolved yet at boot."""
    from azure.identity import DefaultAzureCredential
    from app.core.tenant_store import TableStorageTenantStore
    if not settings.tenant_store_account_url:
        raise RuntimeError("DEPLOYMENT_MODE=shared requires TENANT_STORE_ACCOUNT_URL")  # fail-fast
    return TableStorageTenantStore(
        settings.tenant_store_account_url, settings.tenant_store_table, DefaultAzureCredential()
    )


def resolve_tenant(user, store) -> None:
    """Authorization choke point: onboarded+active tid → set _current_tenant, else 403."""
    from app.core.tenant import set_current_tenant
    rec = store.get(getattr(user, "tid", None))
    if rec is None or rec.status != "active":
        raise HTTPException(status_code=403, detail="tenant not onboarded")
    set_current_tenant(rec)
```

(c) In the shared branch of `require_user`, after setting `_current_user`, call
`resolve_tenant(user, _tenant_store)` (build `_tenant_store` once at module load **only when**
`deployment_mode == "shared"`). Also `set_provider(MultiTenantConfigProvider())` at boot in
shared mode; SingleTenant stays the default. Keep the auth-off no-op `require_user` unchanged.

> Fail-fast: if `deployment_mode == "shared"` and the store can't be built, raise at boot.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run python -m eval.tenant_resolution_test`
Expected: PASS — `✅ tenant resolution + deny path holds.`

- [ ] **Step 5: Re-run the zero-behavior-change gate (self-hosted unaffected)**

Run: `uv run python -m eval.memory_scope_test && uv run python -m eval.tenant_provider_test`
Expected: PASS — single-tenant behavior unchanged.

- [ ] **Step 6: Commit**

```bash
git add apps/backend/app/core/auth.py apps/backend/eval/tenant_resolution_test.py
git commit -m "feat(tenant): multi-tenant scheme + require_user tenant resolution + onboarded deny path"
```

---

## Chunk 3: Step 3 — prove it (infra-gated E2E)

### Task 7: Second-tenant end-to-end

Needs `azd up` (Foundry + Storage) + two Entra test tenants. Can't be validated offline; written now, run when infra + tenants exist.

**Files:**
- Create: `apps/backend/eval/tenant_e2e_test.py`

- [ ] **Step 1: Write the E2E test** — `DEPLOYMENT_MODE=shared`, two tenants onboarded in the Table store, assert: (a) a token from tenant A resolves A's config; (b) a token from tenant B resolves B's; (c) a token from an un-onboarded tenant → 403; (d) `iss` mismatch → rejected; (e) memory_scope is `tidA:oid` vs `tidB:oid`. Acquire the two tenants' tokens via the existing test-credential pattern (see `eval/access_control_test.py` for the ROPC token-acquisition shape).

> **Prereq:** assertion (d) (`iss` validation) can only pass once the `iss_callable` TODO in Task 6
> is resolved against the installed `fastapi_azure_auth` version. Close that TODO before running
> this E2E, or the `iss`-mismatch case won't reject as expected.

- [ ] **Step 2: Run it (infra + two tenants required)**

Run: `DEPLOYMENT_MODE=shared MCP_ENABLED=0 uv run python -m eval.tenant_e2e_test`
Expected: PASS — per-tenant isolation proven. *(Infra-gated: this is the one task needing `azd up` + two Entra tenants; Chunks 1–2 stay green offline regardless.)*

- [ ] **Step 3: Commit**

```bash
git add apps/backend/eval/tenant_e2e_test.py
git commit -m "test(tenant): second-tenant E2E (tid resolution, iss, deny, isolation)"
```

---

## Done criteria

- **Chunk 1** (infra-free): `tenant_provider_test` + `memory_scope_test` green; existing evals still green + clean boot (zero behavior change).
- **Chunk 2** (infra-free unit): `tenant_store_test` + `tenant_resolution_test` green; single-tenant evals still green.
- **Chunk 3** (needs infra + two tenants): `tenant_e2e_test` green — per-tenant config + memory isolation, deny path, iss validation.
