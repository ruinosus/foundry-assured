# Sub-project C — Credential Brokering + Write Governance Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the platform agent's MCP tools driven by the tenant's `Connection` records (B), with Microsoft-native credential resolution (OBO for Microsoft-audience; Foundry connections for the rest — never read a secret), per-tool RBAC (registry × Connection, stricter-of-both), and write tools gated by native tool-approval (Approver/Admin).

**Architecture:** Mode-aware `build_mcp_tools`: **self-hosted keeps today's registry+flat-field build (the Learn E2E stays green); shared becomes connection-driven.** Per connection: map `kind`→registry server, apply `visible_tools_for` RBAC, resolve the credential, set per-tool `approval_mode` (write=always_require). Several pieces are **verification-gated** (the `MCPSpecificApproval` shape, the `azure-ai-projects` get-connection-credentials call, bug #3199) and **infra-gated** (hosted path, internal SDK-broker, AG-UI approval).

**Tech Stack:** `agent_framework` (`MCPStreamableHTTPTool.approval_mode`, hosted `get_mcp_tool`), `azure-ai-projects` (connection credentials), the A-era OBO/RBAC + B-era `TenantStore`/`Connection`, Next.js frontend (`TicketApproval.tsx`).

**Spec:** [`2026-06-29-subproject-c-credential-brokering-design.md`](../specs/2026-06-29-subproject-c-credential-brokering-design.md) · **ADR-009**. Read both first.

**Testing convention (NOT pytest):** runnable `def main()->int` modules in `apps/backend/eval/`, run via `uv run python -m eval.<name>` from `apps/backend/`. Tests target **pure logic** (RBAC, the build against a fake store, the approval-dict construction); live brokering/approval is infra-gated (skips clean). Branch: `feature/saas-c-credential-brokering` (off `develop`, has A+B+MCP). **Don't break the existing self-hosted `mcp_registry_test`/`mcp_connect_test`.**

---

## File Structure

**Backend (modify):**
- `apps/backend/app/agents/mcp/registry.py` — add `visible_tools_for(server, conn, roles)` (stricter-of-both, reuses `_granted`); expose a `server_for_kind(kind)` lookup.
- `apps/backend/app/agents/mcp/tools.py` — **mode-aware** `build_mcp_tools`; the connection-driven path; the per-tool `approval_mode` dict; the credential mechanisms (OBO reuse, hosted `get_mcp_tool`, internal SDK-broker).
- `apps/backend/app/core/tenant_store.py` — add `Connection.endpoint: str = ""`; mark `keyvault_ref` deprecated (comment; field stays).
- `apps/backend/app/core/tenant.py` — mark the flat `mcp_ado_organization/mcp_github_pat/mcp_azure_url` deprecated (comment; fields stay; shared build no longer reads them).

**Backend (create):**
- `apps/backend/eval/rbac_per_tool_test.py`, `eval/connection_tools_build_test.py` — infra-free.
- `apps/backend/eval/mcp_brokering_e2e_test.py` — infra-gated (skips clean).
- `docs/superpowers/notes/c-verifications.md` — Task 0 findings.

**Frontend (modify):**
- `apps/frontend/components/chat/TicketApproval.tsx` — extend the `request_info` tap to carry `ToolApprovalRequestContent`.

---

## Chunk 0: Verifications (gate the design choices — no behavior change)

### Task 0: Verify the three SDK/bug unknowns, record findings

**Files:** Create `docs/superpowers/notes/c-verifications.md`.

- [ ] **Step 1 — `MCPSpecificApproval` shape:** `cd apps/backend && uv run python -c "import inspect, agent_framework as af; from agent_framework import MCPStreamableHTTPTool as M; print(inspect.signature(M.__init__))"` and inspect the `approval_mode` type. Determine the exact per-tool dict shape (e.g. `{'always_require': [...], 'never_require': [...]}` vs an object). Record it.
- [ ] **Step 2 — `azure-ai-projects` get-connection-with-credentials:** `uv run python -c "import inspect; from azure.ai.projects import AIProjectClient; print([m for m in dir(AIProjectClient) if 'onnection' in m])"` then inspect the `connections` operations for a "get with credentials / include_credentials / list_secrets" call. Record the exact call (or record "NOT available → internal non-OBO is hosted-only").
- [ ] **Step 3 — bug #3199:** check the installed `agent_framework` version + changelog/source for whether `approval_mode=always_require` emits over the AG-UI adapter. Record: fixed? and does the approval surface as a `request_info`-style CUSTOM event (the shape `TicketApproval.tsx` consumes)?
- [ ] **Step 4 — write the findings** to `docs/superpowers/notes/c-verifications.md` (a short table: unknown → finding → impact on the plan). Commit:
```bash
git add docs/superpowers/notes/c-verifications.md
git commit -m "docs(c): record SDK/bug verifications (MCPSpecificApproval, azure-ai-projects creds, #3199)"
```

> The later tasks reference these findings. If a call is unavailable, the corresponding path stays infra-gated/deferred — do NOT invent a signature.

---

## Chunk 1: RBAC + the mode-aware connection-driven build (infra-free core)

### Task 1: `visible_tools_for` + `server_for_kind`

**Files:** Modify `apps/backend/app/agents/mcp/registry.py`; Test `apps/backend/eval/rbac_per_tool_test.py`.

- [ ] **Step 1: failing test** — `apps/backend/eval/rbac_per_tool_test.py`:

```python
"""Per-tool RBAC: stricter-of-both (registry min-role AND Connection min-role). Infra-free.

    uv run python -m eval.rbac_per_tool_test
"""

from __future__ import annotations

import sys

from app.agents.mcp.registry import get_server, server_for_kind, visible_tools_for
from app.core.tenant_store import Connection


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {name}")
        if not cond:
            failures.append(name)

    azdo = get_server("azdo")  # read_tools + write_tools; min_role=Reader, min_role_write=Author
    base = Connection(id="c", kind="azdo", label="ADO")  # min_role_read=Reader, min_role_write=Author

    # Reader sees reads, not writes (registry write floor = Author).
    r_reads, r_writes = visible_tools_for(azdo, base, {"Reader"})
    check("Reader sees azdo reads", r_reads == list(azdo.read_tools))
    check("Reader sees NO writes", r_writes == [])

    # Author sees writes.
    _, a_writes = visible_tools_for(azdo, base, {"Author"})
    check("Author sees azdo writes", a_writes == list(azdo.write_tools))

    # Connection TIGHTENS reads to Author → a Reader now sees no reads (stricter-of-both).
    tight = Connection(id="c", kind="azdo", label="ADO", min_role_read="Author")
    t_reads, _ = visible_tools_for(azdo, tight, {"Reader"})
    check("Connection tightening hides reads from Reader", t_reads == [])
    # ...but Author still sees them.
    t_reads2, _ = visible_tools_for(azdo, tight, {"Author"})
    check("Author still sees tightened reads", t_reads2 == list(azdo.read_tools))

    # server_for_kind maps a Connection.kind to the registry server (or None).
    check("server_for_kind resolves a real id", server_for_kind("github").id == "github")
    check("server_for_kind unknown → None", server_for_kind("nope") is None)

    if failures:
        print(f"\n❌ {len(failures)} assertion(s) failed.")
        return 1
    print("\n✅ per-tool RBAC holds.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: run — FAIL** (`ImportError: cannot import name 'visible_tools_for'`).

- [ ] **Step 3: implement in `registry.py`**:

```python
def server_for_kind(kind: str) -> "McpServer | None":
    for s in SERVERS:
        if s.id == kind:
            return s
    return None


def visible_tools_for(server: "McpServer", conn, roles: set[str]) -> tuple[list[str], list[str]]:
    """Tools visible for this caller — stricter-of-both: the registry's min-role AND the
    Connection's min-role must both be satisfied (the tenant can only tighten, never loosen)."""
    reads = (
        list(server.read_tools)
        if _granted(roles, server.min_role) and _granted(roles, conn.min_role_read)
        else []
    )
    writes = (
        list(server.write_tools)
        if _granted(roles, server.min_role_write) and _granted(roles, conn.min_role_write)
        else []
    )
    return reads, writes
```

> Importing `Connection` would create a registry→tenant_store cycle, so `conn` is untyped (duck-typed: it just needs `.min_role_read`/`.min_role_write`). Add a comment.

- [ ] **Step 4: run — PASS.** **Step 5: regression** `uv run python -m eval.mcp_registry_test` (still green). **Commit:**
```bash
git add apps/backend/app/agents/mcp/registry.py apps/backend/eval/rbac_per_tool_test.py
git commit -m "feat(c): per-tool RBAC (visible_tools_for, stricter-of-both) + server_for_kind"
```

### Task 2: `Connection.endpoint` + deprecation comments

**Files:** Modify `app/core/tenant_store.py`, `app/core/tenant.py`.

- [ ] **Step 1:** add `endpoint: str = ""` to `Connection` (after `label`), with a comment: `# per-connection target, e.g. the Azure DevOps org that fills the registry URL {org}`. Mark `keyvault_ref` deprecated (comment: `# DEPRECATED (C/ADR-009): build no longer reads it; kept for back-compat`).
- [ ] **Step 2:** in `app/core/tenant.py`, add a deprecation comment above `mcp_ado_organization/mcp_github_pat/mcp_azure_url`: `# DEPRECATED (C): the shared-mode build reads per-tenant Connections instead; kept for self-hosted back-compat`.
- [ ] **Step 3:** regression — `uv run python -m eval.connection_store_test`, `mcp_registry_test` (the new `endpoint` field defaults to `""` so existing records round-trip; confirm). **Commit:**
```bash
git add apps/backend/app/core/tenant_store.py apps/backend/app/core/tenant.py
git commit -m "feat(c): Connection.endpoint + deprecate keyvault_ref/flat mcp_* fields"
```

### Task 3: mode-aware `build_mcp_tools` — add the connection-driven (shared) path

**Files:** Modify `apps/backend/app/agents/mcp/tools.py`; Test `apps/backend/eval/connection_tools_build_test.py`.

The KEY correctness rule: **self-hosted behavior is unchanged** (the existing registry+flat-field `_build_one(server, roles)` path stays — the Learn E2E depends on it). Add a NEW connection-driven path used only in shared mode.

- [ ] **Step 1: failing test** (the shared/connection path against a fake store + a patched provider):

`apps/backend/eval/connection_tools_build_test.py`:

```python
"""Connection-driven build (shared mode), infra-free: maps Connections → tools, applies per-tool
RBAC, and sets approval_mode (write=always_require). Uses an in-memory store + a public server so
no network/credential is needed.

    uv run python -m eval.connection_tools_build_test
"""

from __future__ import annotations

import sys

from app.agents.mcp import tools as T
from app.core.tenant import set_current_tenant
from app.core.tenant_store import Connection, InMemoryTenantStore, TenantRecord
from app.core.tenant import TenantConfig


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {name}")
        if not cond:
            failures.append(name)

    # A tenant with one enabled 'learn' connection (public — no credential).
    store = InMemoryTenantStore()
    conn = Connection(id="l", kind="learn", label="Learn", enabled=True)
    store.put(TenantRecord(tid="t1", name="t", tier="shared", status="active",
                           data_plane=TenantConfig(), connections=(conn,)))
    set_current_tenant(store.get("t1"))

    built = T.build_from_connections(store.get("t1").connections, {"Admin"})
    check("one tool built for the learn connection", len(built) == 1)
    check("disabled connection yields nothing",
          T.build_from_connections((Connection(id="x", kind="learn", label="L", enabled=False),), {"Admin"}) == [])
    check("unknown kind yields nothing",
          T.build_from_connections((Connection(id="x", kind="bogus", label="B"),), {"Admin"}) == [])
    # A Reader sees the learn read tools (learn min_role=Reader); RBAC wired.
    check("reader gets the public read tools",
          len(T.build_from_connections((conn,), {"Reader"})) == 1)

    set_current_tenant(None)
    if failures:
        print(f"\n❌ {len(failures)} assertion(s) failed.")
        return 1
    print("\n✅ connection-driven build holds.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: run — FAIL** (`AttributeError: module ... has no attribute 'build_from_connections'`).

- [ ] **Step 3: implement** in `tools.py`:
  (a) Add `build_from_connections(conns, roles) -> list[MCPStreamableHTTPTool]`: for each `conn` with `conn.enabled`, `server = server_for_kind(conn.kind)` (skip if None), compute `reads, writes = visible_tools_for(server, conn, roles)`, skip if no tools, resolve the URL (use `conn.endpoint` to fill `{org}` if templated, else `server.url`), build the tool with `allowed_tools=reads+writes` and the `approval_mode` dict (Task 4 sets the real dict; for now `"never_require"` keeps reads working), and the credential header (Task 5). For the public `learn` server, no header. Return the non-None tools.
  (b) Make `build_mcp_tools()` **mode-aware**: `if settings.deployment_mode == "shared": return build_from_connections(_current_tenant_connections(), roles)` (where `_current_tenant_connections()` reads `app.core.auth._tenant_store.get(current_tenant_id()).connections`, or `()` if no store/record); `else:` keep the EXISTING registry path unchanged (`[_build_one(s, roles) for s in enabled_servers()]`).
  Keep `_build_one(server, roles)` (self-hosted) intact; the connection path uses its own builder (or an overload `_build_one(server, roles, conn)` — but do NOT change the self-hosted call site's behavior).

- [ ] **Step 4: run — PASS.** **Step 5: regression (self-hosted unchanged):** `uv run python -m eval.mcp_registry_test` and `MCP_ENABLED=1 ... uv run python -c "import app.main"` (self-hosted boot) green; the existing `mcp_connect_test` (Learn) logic still builds the Learn tool in self-hosted. **Commit:**
```bash
git add apps/backend/app/agents/mcp/tools.py apps/backend/eval/connection_tools_build_test.py
git commit -m "feat(c): mode-aware build — connection-driven in shared, registry path in self-hosted"
```

---

## Chunk 2: Credentials + native write-approval (verification-gated)

### Task 4: per-tool `approval_mode` dict (write=always_require)

**Files:** Modify `tools.py`; extend `connection_tools_build_test.py`.

- [ ] Using the Task-0 `MCPSpecificApproval` finding, set the per-tool `approval_mode` on the connection-built tool: writes → always_require, reads → never_require (the exact shape per Task 0). Add a test asserting the built tool carries always_require for the write tool names (introspect the constructed `approval_mode`). If the shape is uncertain after Task 0, leave a `# TODO: confirm MCPSpecificApproval shape` and use the documented form. Commit.

### Task 5: credential mechanisms (OBO reuse + internal SDK-broker, gated)

**Files:** Modify `tools.py`.

- [ ] **OBO** — for `server.auth == "obo"`, reuse `_obo_header_provider(server.obo_scope)` (unchanged from today). Test: a built `azdo` tool (with an endpoint org) gets an OBO `header_provider` (mock `credential_for_request`).
- [ ] **Internal SDK-broker (gated on Task-0 Step 2)** — for non-OBO with `conn.foundry_connection_id`, IF the `azure-ai-projects` call exists: a `header_provider` that fetches the connection credential at runtime and returns the bearer. IF NOT available: skip non-OBO on the internal path (return None with a logged "needs hosted") and mark this sub-task deferred in `c-verifications.md`. **Do not invent the SDK call.**
- [ ] Commit each with its test.

### Task 6: hosted path (greenfield, infra-gated)

**Files:** Modify `tools.py`.

- [ ] Add a hosted builder: in hosted mode, build tools via `FoundryChatClient.get_mcp_tool(name, url, approval_mode, headers, allowed_tools, project_connection_id=conn.foundry_connection_id)` (verify the kwarg name). This is **greenfield + infra-gated** — write it, unit-test the argument assembly with a fake (no live Foundry), and gate the live validation to the E2E. Commit.

---

## Chunk 3: Frontend approval card (verification-gated)

### Task 7: extend `TicketApproval.tsx` for `ToolApprovalRequestContent`

**Files:** Modify `apps/frontend/components/chat/TicketApproval.tsx`.

- [ ] **Read `TicketApproval.tsx` first.** Per Task-0 Step 3, extend its `request_info` CUSTOM-event tap to ALSO recognize a `ToolApprovalRequestContent` payload (tool name + args), render an approve/reject card, and resume via the existing `agent.runAgent({ resume })`. If Task 0 found the native approval surfaces as a DIFFERENT event shape (or #3199 unfixed), scope the new event handling here (a new branch in the tap) rather than assuming the same shape. `tsc --noEmit` clean. Commit.

---

## Chunk 4: E2E (infra-gated)

### Task 8: brokering E2E (skips clean offline)

**Files:** Create `apps/backend/eval/mcp_brokering_e2e_test.py`.

- [ ] Write the E2E: `DEPLOYMENT_MODE=shared` + a live Foundry project + a real Connection (OBO and/or `foundry_connection_id`); assert the tools build with real credentials and a write tool triggers the approval flow. **Skips clean** (print a skip note, exit 0) when the env is absent — mirror `eval/tenant_admin_e2e_test.py`. Commit.

---

## Done criteria

- **Chunk 0:** `c-verifications.md` records the 3 findings (drives the gated tasks).
- **Chunk 1** (infra-free): `rbac_per_tool_test` + `connection_tools_build_test` green; `mcp_registry_test` still green; **self-hosted boot + Learn build unchanged**.
- **Chunk 2:** approval-dict + OBO unit-tested; the internal SDK-broker either implemented (if the call exists) or cleanly deferred per Task 0.
- **Chunk 3:** `tsc` clean; the approval tap handles the verified event shape.
- **Chunk 4** (needs infra): `mcp_brokering_e2e_test` skips clean offline.
