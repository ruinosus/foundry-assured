# Sub-project B — Connections Store + UI Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The per-tenant management plane — a tenant Admin self-onboards (Admin role + platform allow-list) and manages their data-plane pointers + `Connection` records (references to Foundry connections / Key Vault, **never secrets, no OAuth**), persisted in sub-project A's `TenantStore`.

**Architecture:** Extend A's `TenantRecord` with an embedded `connections` tuple (JSON in the same Table entity). Add an `onboarding_guard` (Admin + allow-list, does NOT resolve the tenant) to break the onboarding chicken-and-egg. A `/tenant` router (mirroring `app/api/admin.py`) does config + connection CRUD, tenant-scoped on `current_tenant_id()`, mounted only in `shared` mode. A Connections admin page mirrors `admin/users`.

**Tech Stack:** Python 3.12, `fastapi` (`APIRouter`, `Depends`, `Security`), `fastapi_azure_auth`, the A-era `TenantStore`/`TenantConfig`/`auth` machinery, Next.js 15 + MSAL frontend.

**Spec:** [`2026-06-29-subproject-b-connections-design.md`](../specs/2026-06-29-subproject-b-connections-design.md) · **ADR-008** (connections = references to Foundry connections / Key Vault). Read both first.

**Testing convention (NOT pytest):** runnable `def main() -> int:` modules under `apps/backend/eval/` (print `✓`/`✗`, non-zero on failure, `sys.exit(main())`), run via `uv run python -m eval.<name>` from `apps/backend/`. Template: `eval/tenant_store_test.py`. Tests target the **pure logic** (store round-trip, the guard, the connection ops); the FastAPI wiring is verified by clean boot. Branch: `feature/saas-b-connections` (already off `develop`, which has A).

---

## File Structure

**Backend (modify):**
- `apps/backend/app/core/tenant_store.py` — add the `Connection` dataclass; add `connections: tuple[Connection, ...] = ()` to `TenantRecord`; update the Table (de)serialization (a `connections` JSON property); add the pure helpers `validate_kind`, `with_connection`, `without_connection`. *Persistence + the per-record connection ops.*
- `apps/backend/app/core/settings.py` — add `onboarding_allowed_tids: str = ""` + an `allowed_tids` property (parses the CSV → set).
- `apps/backend/app/api/__init__.py` — conditionally include the new `tenant.router` only in `shared` mode.

**Backend (create):**
- `apps/backend/app/core/onboarding.py` — `onboarding_guard` (Admin + allow-list, sets `_current_user`, does NOT resolve the tenant).
- `apps/backend/app/api/tenant.py` — the `/tenant` router (GET/onboard/config/connections).
- `apps/backend/eval/connection_store_test.py`, `eval/connection_ops_test.py`, `eval/onboarding_guard_test.py` — infra-free unit tests.
- `apps/backend/eval/tenant_admin_e2e_test.py` — infra-gated E2E (skips clean offline).

**Frontend (create/modify):**
- `apps/frontend/app/admin/connections/page.tsx` *(new)* — mirrors `app/admin/users/page.tsx`.
- `apps/frontend/components/admin/Connections.tsx` *(new)* — mirrors `components/admin/AdminUsers.tsx` (the fetch-with-token + table/forms pattern).
- `apps/frontend/components/shell/AppShell.tsx` — add the "Connections" admin nav entry (Admin-only, beside "Admin").

---

## Chunk 1: Backend — `Connection`, store extension, onboarding guard

### Task 1: `Connection` + extend `TenantRecord` + Table serialization

**Files:**
- Modify: `apps/backend/app/core/tenant_store.py`
- Test: `apps/backend/eval/connection_store_test.py`

- [ ] **Step 1: Write the failing test**

Create `apps/backend/eval/connection_store_test.py`:

```python
"""TenantRecord with embedded connections round-trips through the in-memory fake (infra-free).

    uv run python -m eval.connection_store_test
"""

from __future__ import annotations

import sys

from app.core.tenant import TenantConfig
from app.core.tenant_store import Connection, InMemoryTenantStore, TenantRecord


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {name}")
        if not cond:
            failures.append(name)

    conn = Connection(id="gh-acme", kind="github", label="Acme GitHub",
                      foundry_connection_id="conn:gh-acme")
    rec = TenantRecord(tid="t1", name="Acme", tier="shared", status="active",
                       data_plane=TenantConfig(), connections=(conn,))
    store = InMemoryTenantStore()
    store.put(rec)
    got = store.get("t1")
    check("record round-trips with its connection", got == rec)
    check("connection is preserved", got.connections[0].foundry_connection_id == "conn:gh-acme")

    # Backward-compatible: a record with no connections still works (default ()).
    bare = TenantRecord(tid="t2", name="B", tier="shared", status="active",
                        data_plane=TenantConfig())
    store.put(bare)
    check("record without connections defaults to ()", store.get("t2").connections == ())

    check("Connection has NO secret field",
          not any(f in Connection.__dataclass_fields__ for f in ("secret", "secret_ref", "auth_method", "pat", "token")))

    if failures:
        print(f"\n❌ {len(failures)} assertion(s) failed.")
        return 1
    print("\n✅ connection store round-trip holds.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run it — confirm FAIL**

Run (from `apps/backend/`): `uv run python -m eval.connection_store_test`
Expected: `ImportError: cannot import name 'Connection' from 'app.core.tenant_store'`.

- [ ] **Step 3: Implement in `tenant_store.py`**

Add the `Connection` dataclass (above `TenantRecord`):

```python
@dataclass(frozen=True)
class Connection:
    id: str
    kind: str                          # a registry server id VERBATIM: github | azdo | azure | entra | learn | m365
    label: str
    foundry_connection_id: str = ""    # the Foundry project connection that brokers auth (Microsoft-native)
    keyvault_ref: str = ""             # alternative: the customer's Key Vault URI
    min_role_read: str = "Reader"
    min_role_write: str = "Author"
    enabled: bool = True
    # NO secret / auth_method — Foundry connections / Key Vault authenticate (ADR-005/008).
```

Add `connections` to `TenantRecord`:

```python
@dataclass(frozen=True)
class TenantRecord:
    tid: str
    name: str
    tier: str
    status: str
    data_plane: TenantConfig
    connections: tuple[Connection, ...] = ()   # NEW
```

Update `TableStorageTenantStore` (de)serialization. In `put`, add a `connections` JSON property:

```python
    def put(self, rec: TenantRecord) -> None:
        self._table.upsert_entity({
            "PartitionKey": rec.tid, "RowKey": "config",
            "name": rec.name, "tier": rec.tier, "status": rec.status,
            "data_plane": json.dumps(asdict(rec.data_plane)),
            "connections": json.dumps([asdict(c) for c in rec.connections]),
        })
```

Add a module-level helper to rebuild a record from an entity (used by both `get` and `list`, DRY):

```python
def _record_from_entity(e, tid: str | None = None) -> TenantRecord:
    conns = tuple(Connection(**c) for c in json.loads(e.get("connections") or "[]"))
    return TenantRecord(
        tid=tid or e["PartitionKey"], name=e["name"], tier=e["tier"], status=e["status"],
        data_plane=TenantConfig(**json.loads(e["data_plane"])),
        connections=conns,
    )
```

Replace the inline `TenantRecord(...)` in both methods: in `get` call **`_record_from_entity(e, tid)`** (pass the `tid` param the method already has — don't rely on the entity echoing `PartitionKey`); in `list` call `_record_from_entity(e)` (it reads `e["PartitionKey"]`, which `list_entities` returns).

> `asdict` on a `Connection` is clean (all scalar fields). `e.get("connections") or "[]"` keeps **backward compatibility** with A-era entities that have no `connections` property.

- [ ] **Step 4: Run it — confirm PASS**

Run: `uv run python -m eval.connection_store_test`
Expected: all `✓`, `✅ connection store round-trip holds.`

- [ ] **Step 5: Regression + commit**

```bash
cd /Users/jefferson.barnabe/projects/foundry-helpdesk/apps/backend
uv run python -m eval.tenant_store_test   # A's test still green
cd /Users/jefferson.barnabe/projects/foundry-helpdesk
git add apps/backend/app/core/tenant_store.py apps/backend/eval/connection_store_test.py
git commit -m "feat(connections): Connection entity + connections on TenantRecord (Table round-trip)"
```

### Task 2: Connection ops — `validate_kind` / `with_connection` / `without_connection`

**Files:**
- Modify: `apps/backend/app/core/tenant_store.py`
- Test: `apps/backend/eval/connection_ops_test.py`

- [ ] **Step 1: Write the failing test**

Create `apps/backend/eval/connection_ops_test.py`:

```python
"""Pure connection ops: validate_kind against the registry catalog; add/remove returns a new
TenantRecord (frozen, immutable). Infra-free.

    uv run python -m eval.connection_ops_test
"""

from __future__ import annotations

import sys

from app.core.tenant import TenantConfig
from app.core.tenant_store import (
    Connection, TenantRecord, validate_kind, with_connection, without_connection,
)


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {name}")
        if not cond:
            failures.append(name)

    check("a real registry id validates", validate_kind("github") and validate_kind("azdo"))
    check("a bogus kind is rejected", not validate_kind("not_a_server") and not validate_kind("mcp_github"))

    rec = TenantRecord(tid="t1", name="Acme", tier="shared", status="active",
                       data_plane=TenantConfig())
    c1 = Connection(id="c1", kind="github", label="GH")
    rec2 = with_connection(rec, c1)
    check("with_connection adds it", rec2.connections == (c1,))
    check("original record is unchanged (frozen)", rec.connections == ())

    rec3 = without_connection(rec2, "c1")
    check("without_connection removes it", rec3.connections == ())

    if failures:
        print(f"\n❌ {len(failures)} assertion(s) failed.")
        return 1
    print("\n✅ connection ops hold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run — confirm FAIL** (`ImportError: cannot import name 'validate_kind'`).

- [ ] **Step 3: Implement the pure ops in `tenant_store.py`**

```python
from dataclasses import replace
from app.agents.mcp.registry import SERVERS  # the catalog (servers-as-data)


def validate_kind(kind: str) -> bool:
    """True if `kind` is a registry server id (the catalog is the source of truth)."""
    return any(s.id == kind for s in SERVERS)


def with_connection(rec: TenantRecord, conn: Connection) -> TenantRecord:
    """Return a new record with `conn` added/replaced (by id)."""
    others = tuple(c for c in rec.connections if c.id != conn.id)
    return replace(rec, connections=others + (conn,))


def without_connection(rec: TenantRecord, conn_id: str) -> TenantRecord:
    """Return a new record with the connection `conn_id` removed."""
    return replace(rec, connections=tuple(c for c in rec.connections if c.id != conn_id))
```

> `SERVERS` import: `app.agents.mcp.registry` has no heavy imports (pure data), so importing it in `tenant_store.py` is safe and cycle-free.

- [ ] **Step 4: Run — confirm PASS.**

- [ ] **Step 5: Commit**

```bash
git add apps/backend/app/core/tenant_store.py apps/backend/eval/connection_ops_test.py
git commit -m "feat(connections): pure ops (validate_kind/with_connection/without_connection)"
```

### Task 3: `onboarding_allowed_tids` setting + `onboarding_guard`

**Files:**
- Modify: `apps/backend/app/core/settings.py`
- Create: `apps/backend/app/core/onboarding.py`
- Test: `apps/backend/eval/onboarding_guard_test.py`

- [ ] **Step 1: Add the setting** — in `apps/backend/app/core/settings.py`, add to `PlatformSettings`:

```python
    # Tenants permitted to self-onboard (CSV of tids) — controlled rollout. WE control this.
    onboarding_allowed_tids: str = ""

    @property
    def allowed_tids(self) -> set[str]:
        return {t.strip() for t in self.onboarding_allowed_tids.split(",") if t.strip()}
```

- [ ] **Step 2: Write the failing test**

Create `apps/backend/eval/onboarding_guard_test.py`:

```python
"""onboarding_guard: Admin + allow-list → ok (sets _current_user); missing either → 403.
Does NOT resolve the tenant (so it works pre-onboarding). Infra-free.

    uv run python -m eval.onboarding_guard_test
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

from fastapi import HTTPException

from app.core import auth, onboarding
from app.core.settings import settings


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {name}")
        if not cond:
            failures.append(name)

    # Allow-list = {t-ok}; Admin role required.
    settings.onboarding_allowed_tids = "t-ok"
    admin_ok = SimpleNamespace(tid="t-ok", roles=["Admin"], oid="u1")

    onboarding.onboarding_guard(admin_ok)
    check("Admin + allow-listed passes", auth.current_user() is admin_ok)

    def denies(user) -> bool:
        try:
            onboarding.onboarding_guard(user)
            return False
        except HTTPException as e:
            return e.status_code == 403

    check("non-Admin → 403", denies(SimpleNamespace(tid="t-ok", roles=["Reader"], oid="u")))
    check("Admin but not allow-listed → 403", denies(SimpleNamespace(tid="t-other", roles=["Admin"], oid="u")))
    check("missing tid claim → 403 (not 500)", denies(SimpleNamespace(roles=["Admin"], oid="u")))

    settings.onboarding_allowed_tids = ""
    if failures:
        print(f"\n❌ {len(failures)} assertion(s) failed.")
        return 1
    print("\n✅ onboarding guard holds.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Run — confirm FAIL** (`ModuleNotFoundError: app.core.onboarding`).

- [ ] **Step 4: Implement `app/core/onboarding.py`**

```python
"""The onboarding guard — gates self-service tenant creation.

Separate from require_user (which resolves the tenant and would 403 pre-onboarding). It
authenticates via the scheme, stashes the user in the contextvar (so the handler reads the tid),
and checks the two gates — Admin app role (granted by the customer's Entra) AND the platform
allow-list (we control it) — but does NOT resolve the tenant.
"""

from __future__ import annotations

from fastapi import HTTPException, Security
from fastapi_azure_auth.user import User

from app.core.auth import _current_user, azure_scheme
from app.core.settings import settings


def onboarding_guard(user: User = Security(azure_scheme)) -> User:  # type: ignore[arg-type]
    _current_user.set(user)  # so POST /onboard reads the caller's tid
    if "Admin" not in (getattr(user, "roles", None) or []):
        raise HTTPException(status_code=403, detail="requires Admin")
    if getattr(user, "tid", None) not in settings.allowed_tids:
        raise HTTPException(status_code=403, detail="tenant not allow-listed")
    return user
```

> Imports `_current_user` + `azure_scheme` from `auth.py` (auth does NOT import onboarding → no cycle).

- [ ] **Step 5: Run — confirm PASS. Commit**

```bash
cd /Users/jefferson.barnabe/projects/foundry-helpdesk
git add apps/backend/app/core/settings.py apps/backend/app/core/onboarding.py apps/backend/eval/onboarding_guard_test.py
git commit -m "feat(onboarding): allow-list setting + onboarding_guard (Admin + allow-list, no resolution)"
```

---

## Chunk 2: Backend — the `/tenant` API

### Task 4: The `/tenant` router

**Files:**
- Create: `apps/backend/app/api/tenant.py`
- Modify: `apps/backend/app/api/__init__.py`

- [ ] **Step 1: Implement `app/api/tenant.py`** (mirrors `app/api/admin.py` structure)

```python
"""Per-tenant management API (shared mode) — config + connections, Admin-gated + tenant-scoped.

GET /tenant uses require_role("Admin") ALONE (it must tolerate a not-yet-onboarded tenant —
require_user would resolve the tenant and 403). The config/connection endpoints use require_user
(they require an onboarded tenant) + Admin. Every write is a read-modify-write of the caller's
own record (current_tenant_id()); no tid comes from the path. See the sub-project B design.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Security
from fastapi_azure_auth.user import User
from pydantic import BaseModel

from app.core.auth import _current_user, azure_scheme, require_role, require_user
from app.core.onboarding import onboarding_guard
from app.core.settings import settings
from app.core.tenant import TenantConfig, current_tenant_id   # current_tenant_id lives in tenant, NOT auth
from app.core.tenant_store import (
    Connection, TenantRecord, validate_kind, with_connection, without_connection,
)

router = APIRouter(prefix="/tenant", tags=["tenant"])
_admin = Depends(require_role("Admin"))
_user_admin = [Depends(require_user), Depends(require_role("Admin"))]

# The store is built at boot in shared mode (auth._tenant_store). Reuse it.
from app.core import auth as _auth


def _store():
    if _auth._tenant_store is None:
        raise HTTPException(503, "tenant store unavailable")
    return _auth._tenant_store


def _my_record() -> TenantRecord:
    rec = _store().get(current_tenant_id())
    if rec is None:
        raise HTTPException(404, "tenant not onboarded")
    return rec


class ConfigBody(BaseModel):
    foundry_project_endpoint: str = ""
    foundry_model: str = "gpt-5-mini"
    azure_search_endpoint: str = ""
    azure_search_knowledge_base: str = "helpdesk-kb"


class ConnectionBody(BaseModel):
    id: str
    kind: str
    label: str
    foundry_connection_id: str = ""
    keyvault_ref: str = ""
    min_role_read: str = "Reader"
    min_role_write: str = "Author"
    enabled: bool = True


@router.get("", dependencies=[_admin])
def get_tenant(user: User = Security(azure_scheme)):  # type: ignore[arg-type]
    """Record if onboarded, else whether the caller MAY onboard. Tolerates no record."""
    _current_user.set(user)
    rec = _store().get(getattr(user, "tid", None))
    if rec is None:
        return {"onboarded": False, "can_onboard": getattr(user, "tid", None) in settings.allowed_tids}
    return {"onboarded": True, "record": rec}


@router.post("/onboard")
def onboard(user: User = Depends(onboarding_guard)):
    """Create the tenant record (idempotent). Gated by Admin + allow-list, not resolution."""
    store = _store()
    tid = getattr(user, "tid", None)
    if store.get(tid) is None:
        store.put(TenantRecord(tid=tid, name=tid, tier="shared", status="active",
                               data_plane=TenantConfig()))
    return {"onboarded": True}


@router.put("/config", dependencies=_user_admin)
def put_config(body: ConfigBody):
    from dataclasses import replace
    rec = _my_record()
    _store().put(replace(rec, data_plane=replace(rec.data_plane, **body.model_dump())))
    return {"ok": True}


@router.get("/connections", dependencies=_user_admin)
def list_connections():
    return {"connections": [c for c in _my_record().connections]}


@router.post("/connections", dependencies=_user_admin)
def add_connection(body: ConnectionBody):
    if not validate_kind(body.kind):
        raise HTTPException(422, f"unknown kind: {body.kind}")
    if not (body.foundry_connection_id or body.keyvault_ref):
        raise HTTPException(422, "a connection needs foundry_connection_id or keyvault_ref")
    conn = Connection(**body.model_dump())
    _store().put(with_connection(_my_record(), conn))
    return {"ok": True}


@router.delete("/connections/{conn_id}", dependencies=_user_admin)
def delete_connection(conn_id: str):
    _store().put(without_connection(_my_record(), conn_id))
    return {"ok": True}
```

> `data_plane` here uses the 4 illustrative fields; if the implementer wants the full `TenantConfig` surface editable, extend `ConfigBody` — but keep YAGNI (the 4 the UI shows).

- [ ] **Step 2: Mount the router only in `shared` mode** — in `apps/backend/app/api/__init__.py`:

```python
from app.core.settings import settings
...
if settings.deployment_mode == "shared":
    from app.api import tenant
    api_router.include_router(tenant.router)
```

- [ ] **Step 3: Boot check (both modes)**

Run (from `apps/backend/`):
- self-hosted (default): `uv run python -c "import app.main; print([r.path for r in app.main.app.routes if '/tenant' in r.path])"` → prints `[]` (router NOT mounted).
- shared: `DEPLOYMENT_MODE=shared uv run python -c "import app.main; print(any('/tenant' in r.path for r in app.main.app.routes))"` → prints `True`.

Expected: `/tenant` mounts only in shared mode. (Clean import in both.)

- [ ] **Step 4: Commit**

```bash
cd /Users/jefferson.barnabe/projects/foundry-helpdesk
git add apps/backend/app/api/tenant.py apps/backend/app/api/__init__.py
git commit -m "feat(tenant): /tenant API (onboard + config + connections), shared-mode only"
```

### Task 5: Tenant-scoping unit test (the security invariant)

**Files:**
- Test: `apps/backend/eval/tenant_scope_test.py`

- [ ] **Step 1: Write the test** — proves the per-record ops only touch the caller's record and the validation rejects bad input. (The HTTP layer is thin; this tests the logic the endpoints call.)

Create `apps/backend/eval/tenant_scope_test.py`:

```python
"""The connection write ops only mutate the targeted record, never another tenant's; bad
input is rejected. Mirrors what the /tenant endpoints do (read-modify-write on one record).

    uv run python -m eval.tenant_scope_test
"""

from __future__ import annotations

import sys

from app.core.tenant import TenantConfig
from app.core.tenant_store import (
    Connection, InMemoryTenantStore, TenantRecord, validate_kind, with_connection,
)


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {name}")
        if not cond:
            failures.append(name)

    store = InMemoryTenantStore()
    for tid in ("t-a", "t-b"):
        store.put(TenantRecord(tid=tid, name=tid, tier="shared", status="active",
                               data_plane=TenantConfig()))

    # Add a connection to t-a (the read-modify-write an endpoint does for current_tenant_id()=="t-a")
    rec_a = store.get("t-a")
    store.put(with_connection(rec_a, Connection(id="c1", kind="github", label="GH")))

    check("t-a got the connection", len(store.get("t-a").connections) == 1)
    check("t-b is untouched", store.get("t-b").connections == ())
    check("bad kind rejected (endpoint would 422)", not validate_kind("evil"))

    if failures:
        print(f"\n❌ {len(failures)} assertion(s) failed.")
        return 1
    print("\n✅ tenant-scoped connection ops hold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run — PASS. Commit**

```bash
git add apps/backend/eval/tenant_scope_test.py
git commit -m "test(tenant): tenant-scoped connection ops never touch another tenant"
```

---

## Chunk 3: Frontend — the Connections page

### Task 6: Connections admin page + nav

**Files:**
- Create: `apps/frontend/app/api/tenant/[...path]/route.ts` (the **backend proxy** — without it every `/api/tenant/*` fetch 404s)
- Create: `apps/frontend/app/admin/connections/page.tsx`, `apps/frontend/components/admin/Connections.tsx`
- Modify: `apps/frontend/components/shell/AppShell.tsx`

- [ ] **Step 1: Read the pattern to mirror**

Read `apps/frontend/app/admin/users/page.tsx`, `apps/frontend/components/admin/AdminUsers.tsx`, AND `apps/frontend/app/api/admin/[...path]/route.ts` — copy their shape: the page is a thin `isAdmin`-gated wrapper; the component does the MSAL-token fetch; the **route handler proxies** to the FastAPI backend (the browser never hits the backend directly). Mirror the **exact fetch-with-token helper** AdminUsers uses (do not invent a new one).

- [ ] **Step 1b: Create the `/api/tenant` proxy** — `apps/frontend/app/api/tenant/[...path]/route.ts`: clone `app/api/admin/[...path]/route.ts` verbatim, change `${BACKEND}/admin/${...}` → `${BACKEND}/tenant/${...}`, and **add a `PUT` export** (the admin proxy only exports GET/POST/DELETE, but `/tenant/config` is a PUT). The shared `proxy()` already forwards the body for non-GET/DELETE, so PUT works once the export exists:

```ts
export async function PUT(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
```

- [ ] **Step 2: `app/admin/connections/page.tsx`** — clone `admin/users/page.tsx`, swapping `AdminUsers` → `Connections` and the copy ("manage connections"). Same `useMyRoles`/`isAdmin` gate + `AppShell`.

- [ ] **Step 3: `components/admin/Connections.tsx`** — three zones (mirror the spec §4 sketch):
  1. **Onboarding banner** — `GET /tenant`; if `!onboarded && can_onboard` → a button calling `POST /tenant/onboard`, then refetch.
  2. **Data-plane form** — fields foundry endpoint/model/KB → `PUT /tenant/config`.
  3. **Connections table** — `GET /tenant/connections`; rows with kind/label/ref/min-roles/enabled + delete (`DELETE /tenant/connections/{id}`); an "Add" form (`POST /tenant/connections`) with `kind` as a dropdown of the registry ids (`github`/`azdo`/`azure`/`entra`/`learn`/`m365`) + `foundry_connection_id`/`keyvault_ref` inputs. **NO secret field.** **Edit = re-POST with the same `id`** (the backend `with_connection` upserts by id — there is no connections-PUT), so the edit button just repopulates the Add form.
  Reuse the AdminUsers fetch/error/loading patterns verbatim.

- [ ] **Step 4: Nav entry** — in `apps/frontend/components/shell/AppShell.tsx`, add `{ href: "/admin/connections", label: "Connections", icon: "🔌" }` to the Admin-only workspace nav (the same `isAdmin(roles)` branch that adds `ADMIN_NAV`).

- [ ] **Step 5: Typecheck**

Run (from `apps/frontend/`): `npx tsc --noEmit`
Expected: exit 0.

- [ ] **Step 6: Commit**

```bash
cd /Users/jefferson.barnabe/projects/foundry-helpdesk
git add "apps/frontend/app/api/tenant/[...path]/route.ts" apps/frontend/app/admin/connections/page.tsx apps/frontend/components/admin/Connections.tsx apps/frontend/components/shell/AppShell.tsx
git commit -m "feat(connections): admin Connections page + /api/tenant proxy, mirrors admin/users"
```

---

## Chunk 4: Infra-gated E2E

### Task 7: Tenant-admin E2E (skips clean offline)

**Files:**
- Create: `apps/backend/eval/tenant_admin_e2e_test.py`

- [ ] **Step 1: Write the E2E** — `DEPLOYMENT_MODE=shared` + a live `TableStorageTenantStore` (TENANT_STORE_ACCOUNT_URL) + an allow-listed test tenant. Assert: onboard creates the record; `PUT /config` updates it; `POST /connections` adds a Connection and `GET /connections` returns it; `DELETE` removes it; a non-allow-listed tid → onboard 403. **Skip clean** (print a skip note, exit 0) when the env (`DEPLOYMENT_MODE!=shared` or no `TENANT_STORE_ACCOUNT_URL`/test token) is absent — mirror `eval/tenant_e2e_test.py`'s skip-gate pattern (read it for the token-acquisition + skip shape).

- [ ] **Step 2: Run offline — must SKIP clean**

Run: `uv run python -m eval.tenant_admin_e2e_test` → prints the skip note, exit 0.

- [ ] **Step 3: Commit**

```bash
git add apps/backend/eval/tenant_admin_e2e_test.py
git commit -m "test(tenant): tenant-admin E2E (infra-gated; skips clean offline)"
```

---

## Done criteria

- **Chunk 1** (infra-free): `connection_store_test`, `connection_ops_test`, `onboarding_guard_test` green; A's `tenant_store_test` still green.
- **Chunk 2** (infra-free): `tenant_scope_test` green; `/tenant` mounts only in `shared` mode; clean boot both modes.
- **Chunk 3**: `tsc` clean; the page mirrors admin/users; no secret field in the UI.
- **Chunk 4** (needs infra): `tenant_admin_e2e_test` skips clean offline; runs onboard→config→connection CRUD with a live store + allow-listed tenant.
