# Sub-project D-runtime Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make shared mode boot and serve multiple tenants — fix the boot-time domain-mounting crash, add per-tenant domain entitlement (DomainAssignment), and wire the platform hosted path as a `/platform-hosted` twin over the Invocations protocol.

**Architecture:** Three pillars, all mode-gated so **self-hosted stays byte-identical**: (1) the four `*_configured()` become mode-aware (shared → mount globally without `tenant_config()` at boot); (2) `TenantRecord.enabled_domains` is a stored license entitlement, seeded at onboarding, enforced by a fail-closed `require_domain` request-time gate, managed via `/tenant/domains`; (3) a `/platform-hosted` route + Invocations SSE bridge skeleton + a registry-driven frontend live/hosted toggle. Per [ADR-010](../../adr/ADR-010-per-tenant-domain-entitlement.md) and the [D-runtime design](../specs/2026-06-29-subproject-d-runtime-design.md).

**Tech Stack:** Python 3.12 / FastAPI / `agent-framework` + `agent-framework-ag-ui` / `azure-ai-projects` (Foundry); Next.js 15 / CopilotKit / `@ag-ui/client`. Tests: runnable `def main() -> int` modules in `apps/backend/eval/`, run via `uv run python -m eval.<name>` from `apps/backend/` — **NO pytest**.

**Branch:** `feature/saas-d-runtime` (already created from `develop`).

---

## File Structure

**Backend (`apps/backend/`):**
- `app/core/tenant.py` — add `DOMAIN_IDS` catalog + `require_domain(domain_id)` gate (reads the module-local `_current_tenant`; sub-depends on `require_user` so the tenant is resolved first).
- `app/core/tenant_store.py` — add `TenantRecord.enabled_domains: tuple[str, ...] = ()` + its Table (de)serialization (mirrors `connections`).
- `app/agents/{concierge,cockpit,selfwiki,platform}.py` — make `_knowledge_configured`/`cockpit_configured`/`selfwiki_configured`/`platform_configured` mode-aware.
- `app/main.py` — a `_domain_deps(id)` helper that appends `require_domain` in shared; apply to each domain endpoint.
- `app/api/tenant.py` — seed `enabled_domains` in `onboard()`; add `GET`/`PUT /tenant/domains` with a `DomainsBody`.
- `app/api/chat.py` — `POST /platform-hosted` mirroring `/helpdesk-hosted`.
- `app/services/hosted.py` — `stream_platform_agui()` Invocations bridge skeleton + a `platform_hosted_agent_name` config field.
- `app/core/tenant.py` (`TenantConfig`) + `_TenantEnv` — add `platform_hosted_agent_name`.
- `eval/` — `domain_gate_test`, `enabled_domains_roundtrip_test`, `configured_mode_test`, `shared_boot_smoke_test`, `domains_api_test`, `platform_hosted_bridge_test` (+ infra-gated `platform_hosted_e2e_test`).

**Frontend (`apps/frontend/`):**
- `lib/domains.ts` — optional `hostedAgentId?: string` on `Domain`; set `hostedAgentId: "platform-hosted"` on the platform entry.
- `app/api/copilotkit/[[...slug]]/route.ts` — register a `platform-hosted` HttpAgent.
- `components/console/AssuranceConsole.tsx` — a live/hosted toggle when the domain has a `hostedAgentId`.
- (The `/api/tenant/[...path]` proxy is already a catch-all — `/tenant/domains` proxies with no new route.)

---

## Chunk 1: Backend core — DomainAssignment storage, the gate, and the mount fix

### Task 0: Verify the Invocations contract + lock the dependency-ordering decision

No code change — a verification task feeding Tasks 4 and 6 (project rule #1: never invent SDK signatures).

- [ ] **Step 1: Verify how `dependencies=` ordering works for the gate**

Decision to lock (resolves design Open Q#2): `require_domain` will declare `require_user` as a **FastAPI sub-dependency** (`Depends(require_user)` in the inner signature), so the dependency graph — not list position — guarantees `require_user` runs first and `_current_tenant` is set before the gate reads it. FastAPI caches `require_user`, so listing it in both `auth_dependencies()` and the gate runs it once. Confirm `require_user` is importable from `app.core.auth` and is the dependency that calls `resolve_tenant` (it is — `apps/backend/app/core/auth.py:119-121`, shared branch). Record: no reliance on `add_agent_framework_fastapi_endpoint` dependency ordering is needed.

- [ ] **Step 2: Verify the hosted Invocations endpoint + envelope**

Check the installed Foundry/agent-framework libraries and docs for the Invocations protocol client and the exact endpoint shape `{project_endpoint}/agents/{name}/endpoint/protocols/invocations`:

```bash
cd apps/backend
uv run python -c "import agent_framework, importlib.metadata as m; print('agent_framework', m.version('agent-framework'))"
uv run python -c "import azure.ai.projects as p, importlib.metadata as m; print('azure-ai-projects', m.version('azure-ai-projects'))"
# search the installed wheels for an Invocations protocol client / helper
uv run python - <<'PY'
import importlib, pkgutil
for mod in ("agent_framework", "agent_framework_ag_ui"):
    try:
        m = importlib.import_module(mod)
        print(mod, "->", [n for _,n,_ in pkgutil.iter_modules(m.__path__) if "invoc" in n.lower() or "host" in n.lower()])
    except Exception as e:
        print(mod, "import failed:", e)
PY
```

Record findings in `docs/superpowers/notes/d-verifications.md` (mirror C's `c-verifications.md`): the verified endpoint shape, whether a first-party Invocations client exists offline, and the SSE request/response envelope **or** an explicit "not determinable offline → bridge stays a clean-error skeleton, real streaming lands with the deployed agent (D-packaging)". Task 6 implements only what this step verifies.

- [ ] **Step 3: Commit the note**

```bash
cd /Users/jefferson.barnabe/projects/foundry-helpdesk
git add docs/superpowers/notes/d-verifications.md
git commit -m "docs(D-runtime): Task 0 — verify Invocations contract + gate dependency ordering"
```

---

### Task 1: `DOMAIN_IDS` + the `require_domain` gate

**Files:**
- Modify: `apps/backend/app/core/tenant.py` (add after the `current_tenant_id` helper, ~line 175)
- Test: `apps/backend/eval/domain_gate_test.py`

- [ ] **Step 1: Write the failing test**

`apps/backend/eval/domain_gate_test.py`:

```python
"""require_domain: entitled domain passes; missing entitlement / no tenant → 403.

Infra-free — fakes _current_tenant directly, no Entra, no store, no network.

    uv run python -m eval.domain_gate_test
"""

from __future__ import annotations

import asyncio
import sys

from fastapi import HTTPException

from app.core.tenant import (
    DOMAIN_IDS,
    TenantConfig,
    require_domain,
    set_current_tenant,
)
from app.core.tenant_store import TenantRecord


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {name}")
        if not cond:
            failures.append(name)

    check("DOMAIN_IDS is the four-domain catalog",
          DOMAIN_IDS == ("helpdesk", "cockpit", "selfwiki", "platform"))

    # The gate's inner check ignores its (dependency-wiring) arg and reads _current_tenant.
    gate = require_domain("cockpit")

    def allowed(enabled: tuple[str, ...] | None) -> bool:
        rec = None if enabled is None else TenantRecord(
            tid="t", name="t", tier="shared", status="active",
            data_plane=TenantConfig(), enabled_domains=enabled,
        )
        set_current_tenant(rec)
        try:
            asyncio.run(gate(_user=None))
            return True
        except HTTPException as e:
            return e.status_code != 403 and (_ for _ in ()).throw(e)  # unexpected non-403
        except HTTPException:  # unreachable; kept for clarity
            return False

    def denies(enabled: tuple[str, ...] | None) -> bool:
        rec = None if enabled is None else TenantRecord(
            tid="t", name="t", tier="shared", status="active",
            data_plane=TenantConfig(), enabled_domains=enabled,
        )
        set_current_tenant(rec)
        try:
            asyncio.run(gate(_user=None))
            return False
        except HTTPException as e:
            return e.status_code == 403

    check("entitled domain passes", allowed(("cockpit", "helpdesk")))
    check("domain not in entitlement → 403", denies(("helpdesk",)))
    check("empty entitlement → 403", denies(()))
    check("no resolved tenant → 403", denies(None))

    set_current_tenant(None)
    if failures:
        print(f"\n❌ {len(failures)} assertion(s) failed.")
        return 1
    print("\n✅ require_domain gate holds (fail-closed).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

> Note: the `allowed()` helper above is fiddly because `require_domain` returns a coroutine fn. Simplify in Step 3's test if cleaner — the load-bearing assertions are the four `check(...)` lines. Keep `denies(...)` exactly; for `allowed`, a passing call simply must not raise.

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd apps/backend && uv run python -m eval.domain_gate_test
```
Expected: FAIL — `ImportError: cannot import name 'DOMAIN_IDS'` (and `require_domain`).

- [ ] **Step 3: Implement the gate in `app/core/tenant.py`**

Add after `current_tenant_id()` (~line 175), before the provider wiring:

```python
# The registered agent domains (shared mode mounts all; entitlement gates per tenant).
DOMAIN_IDS: tuple[str, ...] = ("helpdesk", "cockpit", "selfwiki", "platform")


def require_domain(domain_id: str):
    """Shared-mode per-tenant entitlement gate (ADR-010). Fail-closed: 403 unless the
    resolved tenant's enabled_domains contains domain_id.

    Sub-depends on require_user so FastAPI resolves the tenant (sets _current_tenant)
    before this runs — ordering comes from the dependency graph, not list position.
    Imported lazily (factory call time = route setup) to avoid an import cycle at module load.
    """
    from fastapi import Depends, HTTPException

    from app.core.auth import require_user

    async def _check(_user=Depends(require_user)) -> None:
        rec = _current_tenant.get()
        enabled = getattr(rec, "enabled_domains", None) or ()
        if rec is None or domain_id not in enabled:
            raise HTTPException(status_code=403, detail=f"domain '{domain_id}' not enabled for tenant")

    return _check
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd apps/backend && uv run python -m eval.domain_gate_test
```
Expected: PASS — `✅ require_domain gate holds (fail-closed).` (requires Task 2's `enabled_domains` field; if run before Task 2, the `TenantRecord(...)` kwargs fail — do Task 2 first or together. Recommended: implement Task 2 Step 3 before running this.)

- [ ] **Step 5: Commit**

```bash
cd /Users/jefferson.barnabe/projects/foundry-helpdesk
git add apps/backend/app/core/tenant.py apps/backend/eval/domain_gate_test.py
git commit -m "feat(D-runtime): DOMAIN_IDS + fail-closed require_domain entitlement gate"
```

---

### Task 2: `TenantRecord.enabled_domains` + Table serialization

**Files:**
- Modify: `apps/backend/app/core/tenant_store.py:31-37` (the `TenantRecord` dataclass), `:78-84` (`_record_from_entity`), `:108-114` (`put`)
- Test: `apps/backend/eval/enabled_domains_roundtrip_test.py`

- [ ] **Step 1: Write the failing test**

`apps/backend/eval/enabled_domains_roundtrip_test.py`:

```python
"""enabled_domains survives the Table entity round-trip, and defaults to () on legacy records.

Infra-free — exercises the pure (de)serialization helpers with a dict standing in for a
Table entity (no azure-data-tables, no network).

    uv run python -m eval.enabled_domains_roundtrip_test
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict

from app.core.tenant import TenantConfig
from app.core.tenant_store import TenantRecord, _record_from_entity


def _entity(rec: TenantRecord) -> dict:
    # Mirror TableStorageTenantStore.put's entity shape.
    return {
        "PartitionKey": rec.tid, "RowKey": "config",
        "name": rec.name, "tier": rec.tier, "status": rec.status,
        "data_plane": json.dumps(asdict(rec.data_plane)),
        "connections": json.dumps([asdict(c) for c in rec.connections]),
        "enabled_domains": json.dumps(list(rec.enabled_domains)),
    }


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {name}")
        if not cond:
            failures.append(name)

    rec = TenantRecord(tid="t1", name="n", tier="shared", status="active",
                       data_plane=TenantConfig(), enabled_domains=("helpdesk", "platform"))
    back = _record_from_entity(_entity(rec), "t1")
    check("enabled_domains round-trips", back.enabled_domains == ("helpdesk", "platform"))

    # Legacy record (entity written before D) has no enabled_domains key → defaults to ().
    legacy = {
        "PartitionKey": "t2", "RowKey": "config", "name": "n", "tier": "shared",
        "status": "active", "data_plane": json.dumps(asdict(TenantConfig())),
        "connections": "[]",
    }
    check("legacy entity → enabled_domains == ()", _record_from_entity(legacy, "t2").enabled_domains == ())

    if failures:
        print(f"\n❌ {len(failures)} assertion(s) failed.")
        return 1
    print("\n✅ enabled_domains serialization holds (incl. legacy default).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd apps/backend && uv run python -m eval.enabled_domains_roundtrip_test
```
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'enabled_domains'`.

- [ ] **Step 3: Add the field + serialization**

`TenantRecord` (`tenant_store.py:31-37`) — add the defaulted field **after** `connections`:

```python
@dataclass(frozen=True)
class TenantRecord:
    tid: str
    name: str
    tier: str            # shared | dedicated | self_hosted
    status: str          # active | suspended
    data_plane: TenantConfig
    connections: tuple[Connection, ...] = ()
    enabled_domains: tuple[str, ...] = ()   # NEW (D-runtime) — per-tenant license entitlement (ADR-010)
```

`_record_from_entity` (`tenant_store.py:78-84`) — read it (default `()` for legacy rows):

```python
def _record_from_entity(e, tid: str | None = None) -> TenantRecord:
    conns = tuple(Connection(**c) for c in json.loads(e.get("connections") or "[]"))
    return TenantRecord(
        tid=tid or e["PartitionKey"], name=e["name"], tier=e["tier"], status=e["status"],
        data_plane=TenantConfig(**json.loads(e["data_plane"])),
        connections=conns,
        enabled_domains=tuple(json.loads(e.get("enabled_domains") or "[]")),
    )
```

`TableStorageTenantStore.put` (`tenant_store.py:108-114`) — write it:

```python
    def put(self, rec: TenantRecord) -> None:
        self._table.upsert_entity({
            "PartitionKey": rec.tid, "RowKey": "config",
            "name": rec.name, "tier": rec.tier, "status": rec.status,
            "data_plane": json.dumps(asdict(rec.data_plane)),
            "connections": json.dumps([asdict(c) for c in rec.connections]),
            "enabled_domains": json.dumps(list(rec.enabled_domains)),
        })
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd apps/backend && uv run python -m eval.enabled_domains_roundtrip_test
```
Expected: PASS — `✅ enabled_domains serialization holds (incl. legacy default).`

- [ ] **Step 5: Run the existing store test to confirm no regression**

```bash
cd apps/backend && uv run python -m eval.tenant_store_test
```
Expected: PASS (the defaulted field doesn't break existing records).

- [ ] **Step 6: Commit**

```bash
cd /Users/jefferson.barnabe/projects/foundry-helpdesk
git add apps/backend/app/core/tenant_store.py apps/backend/eval/enabled_domains_roundtrip_test.py
git commit -m "feat(D-runtime): TenantRecord.enabled_domains + Table round-trip (legacy-safe default)"
```

---

### Task 3: Mode-aware `*_configured()`

**Files:**
- Modify: `apps/backend/app/agents/concierge.py:26`, `cockpit.py:26`, `selfwiki.py:26`, `platform.py:24`
- Test: `apps/backend/eval/configured_mode_test.py`

- [ ] **Step 1: Write the failing test**

`apps/backend/eval/configured_mode_test.py`:

```python
"""*_configured() are mode-aware: shared returns True WITHOUT reading tenant_config();
self-hosted reads config exactly as before. The shared path is what lets the app boot
before any tenant is resolved.

Infra-free — monkeypatches settings.deployment_mode and asserts tenant_config() is not called.

    uv run python -m eval.configured_mode_test
"""

from __future__ import annotations

import sys

import app.core.tenant as tenant_mod
from app.core.settings import settings


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {name}")
        if not cond:
            failures.append(name)

    from app.agents.concierge import _knowledge_configured
    from app.agents.cockpit import cockpit_configured
    from app.agents.selfwiki import selfwiki_configured
    from app.agents.platform import platform_configured

    # Trip a landmine: in shared, tenant_config() must NOT be called (no tenant at boot).
    orig_mode = settings.deployment_mode
    orig_tc = tenant_mod.tenant_config
    orig_mcp = settings.mcp_enabled
    called = {"n": 0}

    def boom() -> object:
        called["n"] += 1
        raise RuntimeError("tenant_config() must not be called in shared at boot")

    try:
        settings.deployment_mode = "shared"
        tenant_mod.tenant_config = boom  # type: ignore[assignment]
        settings.mcp_enabled = True

        check("shared: _knowledge_configured True w/o tenant_config", _knowledge_configured() is True)
        check("shared: cockpit_configured True w/o tenant_config", cockpit_configured() is True)
        check("shared: selfwiki_configured True w/o tenant_config", selfwiki_configured() is True)
        check("shared: platform_configured True (mcp_enabled) w/o tenant_config", platform_configured() is True)
        check("shared: tenant_config() never called", called["n"] == 0)

        settings.mcp_enabled = False
        check("shared: platform_configured False when mcp disabled", platform_configured() is False)
    finally:
        settings.deployment_mode = orig_mode
        tenant_mod.tenant_config = orig_tc  # type: ignore[assignment]
        settings.mcp_enabled = orig_mcp

    if failures:
        print(f"\n❌ {len(failures)} assertion(s) failed.")
        return 1
    print("\n✅ *_configured() are mode-aware (shared boots without a tenant).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

> The agent modules call `tenant_config()` imported into their own namespace (`from app.core.tenant import tenant_config`). Patching `tenant_mod.tenant_config` won't rebind those names. So in Step 3, the shared early-return must come **before** any `tenant_config()` call (it does), and the test's landmine instead guards via patching each agent module's reference. Adjust the test to patch `app.agents.concierge.tenant_config` etc. (one per module) — OR simpler: assert the functions return the right bool under shared with `mcp_enabled` toggled, and separately assert the source has the early-return. Keep the bool assertions as the load-bearing checks; drop the call-count landmine if patching per-module is noisy.

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd apps/backend && uv run python -m eval.configured_mode_test
```
Expected: FAIL (shared currently falls through to `tenant_config()`).

- [ ] **Step 3: Add the shared early-return to each `*_configured()`**

Each agent module already imports `settings`. Add the guard as the first line.

`concierge.py:26`:
```python
def _knowledge_configured() -> bool:
    if settings.deployment_mode == "shared":
        return True                       # shared: mount globally; per-tenant decided at request time
    cfg = tenant_config()
    ...                                   # unchanged self-hosted body
```

`cockpit.py:26` and `selfwiki.py:26` — same `if settings.deployment_mode == "shared": return True` as the first line, body unchanged.

`platform.py:24` — preserve the platform-global mcp gate (don't blanket-True it):
```python
def platform_configured() -> bool:
    if settings.deployment_mode == "shared":
        return bool(settings.mcp_enabled)  # shared: mount if MCP is globally on; per-tenant gated at request time
    return bool(settings.mcp_enabled and tenant_config().foundry_project_endpoint)
```

Confirm each module has `from app.core.settings import settings` (concierge/cockpit/selfwiki import it; platform.py:20 imports it). Add the import if any is missing.

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd apps/backend && uv run python -m eval.configured_mode_test
```
Expected: PASS — `✅ *_configured() are mode-aware (shared boots without a tenant).`

- [ ] **Step 5: Commit**

```bash
cd /Users/jefferson.barnabe/projects/foundry-helpdesk
git add apps/backend/app/agents/concierge.py apps/backend/app/agents/cockpit.py apps/backend/app/agents/selfwiki.py apps/backend/app/agents/platform.py apps/backend/eval/configured_mode_test.py
git commit -m "feat(D-runtime): mode-aware *_configured() — shared mounts globally without a tenant"
```

---

### Task 4: Wire the gate in `main.py` + shared-boot smoke test

**Files:**
- Modify: `apps/backend/app/main.py:22-30` (imports), `:57-99` (endpoint registrations)
- Test: `apps/backend/eval/shared_boot_smoke_test.py`

- [ ] **Step 1: Write the failing test**

`apps/backend/eval/shared_boot_smoke_test.py`:

```python
"""Shared mode boots: importing app.main under DEPLOYMENT_MODE=shared + auth + the in-memory
tenant store must NOT raise (the gap this sub-project closes). Infra-free — the memory store
backend means no Azure is touched at boot.

    uv run python -m eval.shared_boot_smoke_test
"""

from __future__ import annotations

import importlib
import os
import sys


def main() -> int:
    # Set the shared-mode env BEFORE importing settings/app for the first time.
    os.environ["DEPLOYMENT_MODE"] = "shared"
    os.environ["AUTH_ENABLED"] = "true"
    os.environ["TENANT_STORE_BACKEND"] = "memory"
    os.environ.setdefault("ENTRA_API_CLIENT_ID", "00000000-0000-0000-0000-000000000000")
    os.environ.setdefault("ENTRA_API_SCOPE", "api://x/access_as_user")

    failures: list[str] = []
    try:
        # Fresh import so module-level boot code runs under the shared env.
        for m in [k for k in list(sys.modules) if k.startswith("app.")]:
            del sys.modules[m]
        main_mod = importlib.import_module("app.main")
        ok = hasattr(main_mod, "app")
        print(f"  {'✓' if ok else '✗'} app.main imported under shared mode")
        if not ok:
            failures.append("app object missing")
    except Exception as exc:  # noqa: BLE001
        print(f"  ✗ import raised: {type(exc).__name__}: {exc}")
        failures.append("import raised")

    if failures:
        print(f"\n❌ shared boot failed.")
        return 1
    print("\n✅ shared mode boots clean (no tenant_config at boot).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd apps/backend && uv run python -m eval.shared_boot_smoke_test
```
Expected: FAIL — import raises (the `*_configured()` gates + provider call `tenant_config()` at boot, which raises `RuntimeError: no tenant resolved`). If Task 3 is already merged, this may instead reach the endpoint registrations; either way it must go green only after Step 3.

- [ ] **Step 3: Add `_domain_deps` and apply it**

`main.py` imports (extend the existing block near `:22-30`):
```python
from fastapi import Depends, FastAPI
from app.core.tenant import require_domain
```

Add the helper after the app + router setup (~after `app.include_router(api_router)`, line 52):
```python
def _domain_deps(domain_id: str) -> list:
    """Auth deps, plus (shared mode only) the per-tenant entitlement gate. In self_hosted/
    dedicated this is exactly auth_dependencies() — byte-identical to today."""
    deps = auth_dependencies()
    if settings.deployment_mode == "shared":
        deps = [*deps, Depends(require_domain(domain_id))]
    return deps
```

Replace each `dependencies=auth_dependencies()` on the four domain endpoints with `dependencies=_domain_deps("<id>")`:
- `/helpdesk` (the `_knowledge_configured()` true-branch, line 62) → `_domain_deps("helpdesk")` (leave the auth-off `else` branch untouched — shared always has auth).
- `/cockpit` (line 76) → `_domain_deps("cockpit")`
- `/selfwiki` (line 86) → `_domain_deps("selfwiki")`
- `/platform` (line 98) → `_domain_deps("platform")`

- [ ] **Step 4: Run the smoke test to verify it passes**

```bash
cd apps/backend && uv run python -m eval.shared_boot_smoke_test
```
Expected: PASS — `✅ shared mode boots clean (no tenant_config at boot).`

- [ ] **Step 5: Confirm self-hosted is unaffected**

```bash
cd apps/backend && DEPLOYMENT_MODE=self_hosted uv run python -c "import app.main; print('self-hosted boots, app:', hasattr(app := __import__('app.main', fromlist=['app']).app, 'router'))"
```
Expected: prints `self-hosted boots, app: True` (default mode path unchanged; `_domain_deps` returns exactly `auth_dependencies()`).

- [ ] **Step 6: Commit**

```bash
cd /Users/jefferson.barnabe/projects/foundry-helpdesk
git add apps/backend/app/main.py apps/backend/eval/shared_boot_smoke_test.py
git commit -m "feat(D-runtime): mount domains globally in shared + gate per-tenant via _domain_deps; shared boots clean"
```

---

## Chunk 2: Backend — onboarding seed + the `/tenant/domains` management API

### Task 5: Seed `enabled_domains` at onboarding + GET/PUT `/tenant/domains`

**Files:**
- Modify: `apps/backend/app/api/tenant.py:21-24` (imports), `:82-90` (`onboard`), end of file (new endpoints + `DomainsBody`)
- Test: `apps/backend/eval/domains_api_test.py`

- [ ] **Step 1: Write the failing test**

`apps/backend/eval/domains_api_test.py`:

```python
"""onboard() seeds enabled_domains=DOMAIN_IDS; GET/PUT /tenant/domains read & tighten it,
tenant-scoped, rejecting unknown ids. Infra-free — drives the route functions with a fake
store + a stubbed current_tenant_id (no Entra, no network).

    uv run python -m eval.domains_api_test
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

from fastapi import HTTPException

from app.core import auth as _auth
import app.api.tenant as tapi
from app.core.tenant import DOMAIN_IDS
from app.core.tenant_store import InMemoryTenantStore


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {name}")
        if not cond:
            failures.append(name)

    store = InMemoryTenantStore()
    _auth._tenant_store = store
    tapi.current_tenant_id = lambda: "t-1"  # type: ignore[assignment]  # stub the resolved tenant

    # onboard seeds all domains
    tapi.onboard(SimpleNamespace(tid="t-1"))
    rec = store.get("t-1")
    check("onboard seeds enabled_domains=DOMAIN_IDS", rec.enabled_domains == DOMAIN_IDS)

    # GET returns catalog + enabled
    got = tapi.get_domains()
    check("GET catalog == DOMAIN_IDS", tuple(got["catalog"]) == DOMAIN_IDS)
    check("GET enabled == DOMAIN_IDS", tuple(got["enabled"]) == DOMAIN_IDS)

    # PUT tightens to a subset
    tapi.put_domains(tapi.DomainsBody(enabled=["helpdesk", "platform"]))
    check("PUT tightens enabled", store.get("t-1").enabled_domains == ("helpdesk", "platform"))

    # PUT rejects an unknown id
    def rejects_unknown() -> bool:
        try:
            tapi.put_domains(tapi.DomainsBody(enabled=["helpdesk", "bogus"]))
            return False
        except HTTPException as e:
            return e.status_code in (400, 422)

    check("PUT rejects unknown domain id", rejects_unknown())
    check("rejected PUT did not mutate", store.get("t-1").enabled_domains == ("helpdesk", "platform"))

    _auth._tenant_store = None
    if failures:
        print(f"\n❌ {len(failures)} assertion(s) failed.")
        return 1
    print("\n✅ domains API: seed + read + tighten + reject-unknown, tenant-scoped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd apps/backend && uv run python -m eval.domains_api_test
```
Expected: FAIL — `AttributeError: module 'app.api.tenant' has no attribute 'get_domains'` (and `DomainsBody`/`put_domains`).

- [ ] **Step 3: Implement the seed + endpoints**

`tenant.py` imports — add `DOMAIN_IDS`:
```python
from app.core.tenant import TenantConfig, current_tenant_id, DOMAIN_IDS
```

`onboard()` (`:88-89`) — seed the entitlement explicitly (the field defaults to `()`, so without this a new tenant has **zero** domains — fully fail-closed; the seed is what opens the default-all entitlement):
```python
    if store.get(tid) is None:
        store.put(TenantRecord(tid=tid, name=tid, tier="shared", status="active",
                               data_plane=TenantConfig(), enabled_domains=DOMAIN_IDS))
```

Append the body model + endpoints at the end of `tenant.py`:
```python
class DomainsBody(BaseModel):
    enabled: list[str]


@router.get("/domains", dependencies=_user_admin)
def get_domains():
    """The domain catalog + this tenant's entitlement (Admin, tenant-scoped)."""
    return {"catalog": list(DOMAIN_IDS), "enabled": list(_my_record().enabled_domains)}


@router.put("/domains", dependencies=_user_admin)
def put_domains(body: DomainsBody):
    """Tighten/adjust this tenant's domain entitlement. Rejects ids outside the catalog."""
    unknown = [d for d in body.enabled if d not in DOMAIN_IDS]
    if unknown:
        raise HTTPException(422, f"unknown domain(s): {', '.join(unknown)}")
    rec = _my_record()
    # preserve catalog order, dedupe
    enabled = tuple(d for d in DOMAIN_IDS if d in set(body.enabled))
    _store().put(replace(rec, enabled_domains=enabled))
    return {"ok": True}
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd apps/backend && uv run python -m eval.domains_api_test
```
Expected: PASS — `✅ domains API: seed + read + tighten + reject-unknown, tenant-scoped.`

- [ ] **Step 5: Confirm the existing tenant-API tests still pass**

```bash
cd apps/backend && uv run python -m eval.tenant_e2e_test && uv run python -m eval.onboarding_guard_test
```
Expected: PASS (the onboard seed adds a field; existing assertions unaffected). If `tenant_e2e_test` asserts the onboarded record shape, update it to expect `enabled_domains == DOMAIN_IDS`.

- [ ] **Step 6: Commit**

```bash
cd /Users/jefferson.barnabe/projects/foundry-helpdesk
git add apps/backend/app/api/tenant.py apps/backend/eval/domains_api_test.py
git commit -m "feat(D-runtime): seed enabled_domains at onboarding + GET/PUT /tenant/domains (Admin, tenant-scoped)"
```

---

## Chunk 3: The `/platform-hosted` twin + the frontend toggle

### Task 6: `/platform-hosted` route + Invocations bridge skeleton

**Files:**
- Modify: `apps/backend/app/core/tenant.py` (`TenantConfig` + `_TenantEnv`: add `platform_hosted_agent_name`), `apps/backend/app/services/hosted.py` (add `stream_platform_agui`), `apps/backend/app/api/chat.py` (add the route)
- Test: `apps/backend/eval/platform_hosted_bridge_test.py`; infra-gated `apps/backend/eval/platform_hosted_e2e_test.py`

- [ ] **Step 1: Add the config field**

`TenantConfig` (`tenant.py`, after `hosted_agent_name`, ~line 69):
```python
    # D-runtime: the deployed platform hosted agent (Invocations protocol). Empty until deployed.
    platform_hosted_agent_name: str = "platform-concierge"
```
Mirror it in `_TenantEnv` (after its `hosted_agent_name`, ~line 122):
```python
    platform_hosted_agent_name: str = "platform-concierge"
```

- [ ] **Step 2: Write the failing test (the bridge's AG-UI error envelope, infra-free)**

`apps/backend/eval/platform_hosted_bridge_test.py`:

```python
"""The /platform-hosted Invocations bridge emits a well-formed AG-UI SSE envelope and,
when the hosted agent is unreachable/undeployed (no endpoint configured), surfaces a clean
RunErrorEvent instead of crashing. Infra-free — no deployed agent, no network that resolves.

    uv run python -m eval.platform_hosted_bridge_test
"""

from __future__ import annotations

import asyncio
import sys

from app.services.hosted import stream_platform_agui


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {name}")
        if not cond:
            failures.append(name)

    async def collect() -> list[str]:
        out: list[str] = []
        async for chunk in stream_platform_agui({"messages": [{"role": "user", "content": "hi"}]}):
            out.append(chunk)
        return out

    chunks = asyncio.run(collect())
    blob = "".join(chunks)
    check("emits a RUN_STARTED", "RUN_STARTED" in blob or "RunStarted" in blob)
    check("emits a terminal RUN_FINISHED or RUN_ERROR",
          any(t in blob for t in ("RUN_FINISHED", "RUN_ERROR", "RunFinished", "RunError")))
    check("did not raise", True)

    if failures:
        print(f"\n❌ {len(failures)} assertion(s) failed.")
        return 1
    print("\n✅ platform-hosted bridge emits a clean AG-UI envelope (infra-free).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Run the test to verify it fails**

```bash
cd apps/backend && uv run python -m eval.platform_hosted_bridge_test
```
Expected: FAIL — `ImportError: cannot import name 'stream_platform_agui'`.

- [ ] **Step 4: Implement the bridge skeleton**

Add to `app/services/hosted.py`. Mirror `stream_agui`'s AG-UI envelope; the Invocations call is gated by Task 0's verification. If Task 0 verified the contract, implement the streaming POST; otherwise fence it as below so the path is honest and testable.

```python
def _platform_invocations_url() -> str:
    """The deployed platform agent's Invocations endpoint (AG-UI → Invocations, not Responses;
    per the Foundry hosted-agents guidance). Empty endpoint ⇒ not deployed."""
    cfg = tenant_config()
    base = (cfg.foundry_project_endpoint or "").rstrip("/")
    name = cfg.platform_hosted_agent_name
    return f"{base}/agents/{name}/endpoint/protocols/invocations" if base else ""


async def stream_platform_agui(body: dict) -> AsyncGenerator[str]:
    """Stream the deployed PLATFORM hosted agent (Invocations protocol) as AG-UI SSE.

    Twin of stream_agui, but Invocations (raw SSE) — the protocol Microsoft indicates for
    AG-UI — so C's write-approval interrupt can round-trip on the hosted path (Responses can't).

    The deployed agent + its Foundry Toolbox tool config are infra-gated (D-packaging); until the
    Invocations contract is verified (Task 0) and an agent is deployed, an unconfigured endpoint
    surfaces a clean RunErrorEvent rather than crashing.
    """
    from ag_ui.core import (
        RunErrorEvent, RunFinishedEvent, RunStartedEvent,
        TextMessageEndEvent, TextMessageStartEvent,
    )
    from ag_ui.encoder import EventEncoder

    thread_id = body.get("threadId") or body.get("thread_id") or uuid.uuid4().hex
    run_id = body.get("runId") or body.get("run_id") or uuid.uuid4().hex
    enc = EventEncoder()
    yield enc.encode(RunStartedEvent(thread_id=thread_id, run_id=run_id))
    message_id = uuid.uuid4().hex
    yield enc.encode(TextMessageStartEvent(message_id=message_id, role="assistant"))
    try:
        url = _platform_invocations_url()
        if not url:
            raise RuntimeError("platform hosted agent not configured (foundry_project_endpoint empty)")
        # TODO(Task 0 / D-packaging): implement the verified Invocations streaming POST to `url`
        # (raw SSE: forward the AG-UI run, re-emit content deltas + the tool-approval interrupt).
        # Build via _build_hosted_from_connections (C) + the Foundry Toolbox; do NOT invent the
        # envelope — only implement once the contract is verified and an agent is deployed.
        raise NotImplementedError("platform-hosted Invocations bridge pending verified contract + deployed agent")
    except Exception as exc:  # surface to the UI as a clean run error (mirrors stream_agui)
        yield enc.encode(TextMessageEndEvent(message_id=message_id))
        yield enc.encode(RunErrorEvent(message=str(exc), code=type(exc).__name__))
```

- [ ] **Step 5: Add the route in `app/api/chat.py`**

Mirror `/helpdesk-hosted`, adding the shared-mode domain gate:
```python
from app.services.hosted import stream_agui, stream_platform_agui
from app.core.settings import settings


def _hosted_deps(domain_id: str) -> list:
    deps = auth_dependencies()
    if settings.deployment_mode == "shared":
        from app.core.tenant import require_domain
        from fastapi import Depends
        deps = [*deps, Depends(require_domain(domain_id))]
    return deps


@router.post("/platform-hosted", dependencies=_hosted_deps("platform"))
async def platform_hosted(request: Request) -> StreamingResponse:
    """AG-UI twin of /platform — the deployed platform hosted agent over the Invocations
    protocol, streamed as AG-UI. Same Entra gate (+ shared-mode domain entitlement)."""
    body = await request.json()
    return StreamingResponse(stream_platform_agui(body), media_type="text/event-stream")
```
> Keep `/helpdesk-hosted`'s `dependencies=auth_dependencies()` as-is (helpdesk has no shared-mode gate need for this slice; entitlement on the hosted helpdesk twin is out of scope here).

- [ ] **Step 6: Run the bridge test to verify it passes**

```bash
cd apps/backend && uv run python -m eval.platform_hosted_bridge_test
```
Expected: PASS — `✅ platform-hosted bridge emits a clean AG-UI envelope (infra-free).`

- [ ] **Step 7: Add the infra-gated E2E (skips clean offline)**

`apps/backend/eval/platform_hosted_e2e_test.py` — mirror the skip-clean pattern of `mcp_brokering_e2e_test.py`: if `tenant_config().foundry_project_endpoint` is empty (no deployed agent), print `⏭ skipped (no deployed platform hosted agent)` and `return 0`. Otherwise drive `stream_platform_agui` against the live Invocations endpoint and assert a non-error terminal event + (when a write is requested) the approval interrupt surfaces. This is the real validation of the Invocations path.

- [ ] **Step 8: Commit**

```bash
cd /Users/jefferson.barnabe/projects/foundry-helpdesk
git add apps/backend/app/core/tenant.py apps/backend/app/services/hosted.py apps/backend/app/api/chat.py apps/backend/eval/platform_hosted_bridge_test.py apps/backend/eval/platform_hosted_e2e_test.py
git commit -m "feat(D-runtime): /platform-hosted route + Invocations bridge skeleton (infra-gated E2E)"
```

---

### Task 7: Frontend — register `platform-hosted` + the live/hosted toggle

**Files:**
- Modify: `apps/frontend/lib/domains.ts` (the `Domain` interface + the platform entry), `apps/frontend/app/api/copilotkit/[[...slug]]/route.ts` (register the agent), `apps/frontend/components/console/AssuranceConsole.tsx` (the toggle)

- [ ] **Step 1: Add `hostedAgentId` to the registry**

`lib/domains.ts` — add to the `Domain` interface (after `endpoint`):
```typescript
  /** Optional Foundry hosted twin agent id (live-vs-hosted toggle). */
  hostedAgentId?: string;
```
Set it on the platform entry (after its `endpoint: "/platform"`):
```typescript
    endpoint: "/platform",
    hostedAgentId: "platform-hosted",
```

- [ ] **Step 2: Register the `platform-hosted` HttpAgent**

`app/api/copilotkit/[[...slug]]/route.ts` — add the URL + agent, mirroring `helpdeskHosted`. The platform hosted path carries HITL (the tool-approval interrupt over Invocations), so it uses the **resume bridge**:
```typescript
const PLATFORM_HOSTED_AGUI_URL =
  process.env.PLATFORM_HOSTED_AGUI_URL ?? "http://localhost:8000/platform-hosted";
```
```typescript
const helpdeskHosted = new HttpAgent({ url: HOSTED_AGUI_URL });
const platformHosted = withResumeBridge(PLATFORM_HOSTED_AGUI_URL);
```
```typescript
const runtime = new CopilotRuntime({
  agents: { ...registryAgents, "helpdesk-hosted": helpdeskHosted, "platform-hosted": platformHosted },
});
```

- [ ] **Step 3: Add the live/hosted toggle in `AssuranceConsole.tsx`**

When `domain.hostedAgentId` is set, render a `seg` toggle (mirroring `HelpdeskApp.tsx:56-63`) and switch the `CopilotChat agentId` between `domain.id` (live) and `domain.hostedAgentId` (hosted). Add near the top of the rendering component:
```typescript
import { useState } from "react";  // already imported
const [mode, setMode] = useState<"live" | "hosted">("live");
const activeAgentId = mode === "hosted" && domain.hostedAgentId ? domain.hostedAgentId : domain.id;
```
Render the toggle just above the chat host (only when a twin exists):
```tsx
{domain.hostedAgentId && (
  <div className="seg" style={{ margin: "8px 0" }}>
    <button className={mode === "live" ? "on" : ""} onClick={() => setMode("live")}>Live</button>
    <button className={mode === "hosted" ? "on" : ""} onClick={() => setMode("hosted")}>Hosted</button>
  </div>
)}
<div className="console-chat copilotkit-chat-host">
  <CopilotChat agentId={activeAgentId} />
</div>
```
> Keep it minimal and registry-driven: any future domain that declares `hostedAgentId` gets the toggle for free. Do not special-case "platform" in the component.

- [ ] **Step 4: Build the frontend to verify it compiles**

```bash
cd apps/frontend && npm run build
```
Expected: build succeeds (type-checks `hostedAgentId`, the new agent entry, and the toggle). If `npm run build` is heavy, `npx tsc --noEmit` is an acceptable faster check.

- [ ] **Step 5: Commit**

```bash
cd /Users/jefferson.barnabe/projects/foundry-helpdesk
git add apps/frontend/lib/domains.ts "apps/frontend/app/api/copilotkit/[[...slug]]/route.ts" apps/frontend/components/console/AssuranceConsole.tsx
git commit -m "feat(D-runtime): register platform-hosted twin + registry-driven live/hosted toggle"
```

---

## Final verification

- [ ] **Run the full infra-free D-runtime suite (all green, offline):**

```bash
cd apps/backend
for t in domain_gate enabled_domains_roundtrip configured_mode shared_boot_smoke domains_api platform_hosted_bridge; do
  echo "== $t ==" && uv run python -m eval.${t}_test || exit 1
done
echo "== infra-gated (must skip clean) ==" && uv run python -m eval.platform_hosted_e2e_test
```
Expected: every infra-free test prints `✅`; `platform_hosted_e2e_test` prints `⏭ skipped`.

- [ ] **Confirm no self-hosted regression — run the A/B/C regression tests:**

```bash
cd apps/backend
for t in tenant_store tenant_resolution tenant_provider connection_store rbac_per_tool hosted_build; do
  uv run python -m eval.${t}_test || exit 1
done
```
Expected: all PASS (every D change is mode-gated; self-hosted paths untouched).

- [ ] **Dispatch the final code reviewer** over the whole branch, then proceed to `superpowers:finishing-a-development-branch` to open the PR into `develop`.

---

## Notes for the executor

- **The #1 property is byte-identical self-hosted.** Every change is mode-gated (`settings.deployment_mode == "shared"`). If a change would alter self-hosted behavior, it's wrong — re-scope it behind the shared guard.
- **Fail-closed everywhere.** `enabled_domains` defaults to `()` (zero domains); `require_domain` 403s unless explicitly entitled; `onboard()` is the only place the default-all entitlement is opened, and it's an **explicit** constructor kwarg (the field default won't do it).
- **Tenant-scoping is inviolable.** Every `/tenant/*` write is read-modify-write of `current_tenant_id()`'s own record — no tid from a path, ever.
- **Don't invent SDK signatures (rule #1).** The Invocations bridge (Task 6) implements only what Task 0 verifies; the rest stays a clean-error skeleton until the contract + a deployed agent land (D-packaging).
- **Task ordering:** Task 1's test needs Task 2's field — do Task 2's Step 3 before running Task 1's Step 4 (or implement 1+2 together, then run both tests).
