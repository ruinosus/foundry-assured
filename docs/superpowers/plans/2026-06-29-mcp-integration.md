# Microsoft first-party MCP servers — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the Microsoft first-party MCP servers (Learn, Azure, Entra, Azure DevOps, GitHub, M365) to foundry-assured as a new `platform`/ops domain — internal (agent-framework + OBO) and hosted (Foundry OAuth passthrough) — governed by native `approval_mode` + the existing RBAC, reusing the OBO/HITL/domain-registry machinery.

**Architecture:** A thin **data registry** (`McpServer` records) is the single source that builds the framework's *native* MCP tools — `MCPStreamableHTTPTool` on the internal path, `get_mcp_tool`/toolboxes on the hosted path. A `platform` agent assembles its tool list from the registry, **filtered by the caller's role** (`has_role`/`current_roles`), and is registered over AG-UI like the other domains. Reads need `Reader`+, writes need `Author`/`Admin` and route through our existing HITL approval card (the AG-UI native-approval bug #3199 workaround). The infra-free slice is **Learn MCP** (public, read-only) end-to-end; OBO servers, GitHub, the hosted mirror and M365 are infra-gated follow-on chunks.

**Tech Stack:** Python 3.12, `agent_framework` (`MCPStreamableHTTPTool`, `FoundryChatClient.as_agent`), `agent-framework-ag-ui`, FastAPI, existing `app/core/auth.py` (OBO + RBAC); Next.js 15 + CopilotKit frontend (`lib/domains.ts`, the copilotkit route).

**Spec:** [`docs/MCP-INTEGRATION-PLAN.md`](../../MCP-INTEGRATION-PLAN.md) — read it first; this plan implements it.

**Testing convention (IMPORTANT — not pytest):** this repo has **no pytest**. Tests are self-contained runnable modules under `apps/backend/eval/`, shaped `def main() -> int:` (print `✓`/`✗` per case, return non-zero on failure) with `if __name__ == "__main__": sys.exit(main())`, run via `uv run python -m eval.<name>`. Match that exactly — see `eval/test_attribution.py` as the template. All backend commands run from `apps/backend/`.

---

## File Structure

**Backend (create):**
- `apps/backend/app/agents/mcp/__init__.py` — package marker.
- `apps/backend/app/agents/mcp/registry.py` — the `McpServer` dataclass, the 6 server records, and the **pure** role→visible-tools logic (no network, no framework imports). One responsibility: *what servers/tools exist and who may see them.*
- `apps/backend/app/agents/mcp/tools.py` — builds `MCPStreamableHTTPTool`s from the registry for a request (role filter + auth wiring + approval). Depends on `registry.py` + `app/core/auth.py`. One responsibility: *turn registry data into live framework tools.*
- `apps/backend/app/agents/platform.py` — `platform_configured()` + `build_platform_agent()`. Mirrors `app/agents/selfwiki.py`. One responsibility: *the platform agent.*
- `apps/backend/eval/mcp_registry_test.py` — unit test for the pure registry logic (infra-free).
- `apps/backend/eval/mcp_learn_test.py` — end-to-end proof against the public Learn MCP (network, infra-free).

**Backend (modify):**
- `apps/backend/app/core/settings.py` — add MCP feature flags / env (Learn URL default, `mcp_enabled`).
- `apps/backend/app/agents/prompts.py` — add `PLATFORM_INSTRUCTIONS`.
- `apps/backend/app/main.py` — register the `/platform` AG-UI endpoint (gated on `platform_configured()`).

**Frontend (modify):**
- `apps/frontend/lib/domains.ts` — extend `DomainKind` with `"tool"`; add the `platform` domain entry.
- `apps/frontend/app/api/copilotkit/[[...slug]]/route.ts` — extract a shared `withResumeBridge(url)` factory; register any interrupt-bearing domain (`kind !== "grounded"`) from the registry with that bridge.

---

## Chunk 1: The MCP registry (pure data + role logic)

Infra-free, fully unit-testable. No framework or network imports in `registry.py`.

### Task 1: Registry dataclass + the six server records

**Files:**
- Create: `apps/backend/app/agents/mcp/__init__.py`
- Create: `apps/backend/app/agents/mcp/registry.py`
- Test: `apps/backend/eval/mcp_registry_test.py`

- [ ] **Step 1: Write the failing test** (project convention — runnable module, not pytest)

Create `apps/backend/eval/mcp_registry_test.py`:

```python
"""Unit test for the MCP registry's pure role→visible-tools logic (infra-free).

No network, no framework — asserts the data + the access rules the spec defines:
read needs Reader+, write needs Author/Admin, unclassified tools fail closed (write),
and only m365 is disabled.

    uv run python -m eval.mcp_registry_test
"""

from __future__ import annotations

import sys

from app.agents.mcp.registry import (
    SERVERS,
    get_server,
    classify_tool,
    visible_tools,
)


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {name}")
        if not cond:
            failures.append(name)

    # Registry shape
    ids = {s.id for s in SERVERS}
    check("all six servers present",
          ids == {"learn", "azure", "entra", "azdo", "github", "m365"})
    check("learn is public + read-only + enabled",
          get_server("learn").auth == "public"
          and not get_server("learn").write_tools
          and get_server("learn").enabled)
    check("only m365 is disabled",
          {s.id for s in SERVERS if not s.enabled} == {"m365"})

    azure = get_server("azure")
    # classify_tool: read/write/unknown, fail-closed
    check("a declared read tool classifies read",
          classify_tool(azure, azure.read_tools[0]) == "read")
    check("a declared write tool classifies write",
          classify_tool(azure, azure.write_tools[0]) == "write")
    check("an UNDECLARED tool fails closed to write",
          classify_tool(azure, "azure_totally_new_tool") == "write")

    # visible_tools: role gating
    reader = {"Reader"}
    author = {"Author"}
    none: set[str] = set()
    r_reads, r_writes = visible_tools(azure, reader)
    check("Reader sees azure reads", r_reads == list(azure.read_tools))
    check("Reader sees NO azure writes", r_writes == [])
    a_reads, a_writes = visible_tools(azure, author)
    check("Author sees azure writes", a_writes == list(azure.write_tools))
    check("Author also sees azure reads", a_reads == list(azure.read_tools))
    n_reads, n_writes = visible_tools(azure, none)
    check("no-role caller sees nothing", n_reads == [] and n_writes == [])

    if failures:
        print(f"\n❌ {len(failures)} registry assertion(s) failed.")
        return 1
    print("\n✅ MCP registry logic holds.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run the test to verify it fails**

Run (from `apps/backend/`): `uv run python -m eval.mcp_registry_test`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.agents.mcp'`.

- [ ] **Step 3: Create the package marker**

Create `apps/backend/app/agents/mcp/__init__.py` (empty).

- [ ] **Step 4: Write `registry.py`**

Create `apps/backend/app/agents/mcp/registry.py`:

```python
"""MCP servers as data — the single source for both the internal (MCPStreamableHTTPTool)
and hosted (get_mcp_tool/toolbox) paths. PURE: no network, no framework, no auth imports,
so it's unit-testable in isolation (eval/mcp_registry_test.py).

Governance lives here as data, not code branches: each server declares which tools are
reads vs writes and the minimum role for each. A tool that is on NEITHER list is treated
as a WRITE (fail-closed) — an unclassified new tool can't slip through as an open read.

Role model (flat, not a ladder — see app/core/auth.py APP_ROLES): "read" access is granted
to Reader/Author/Approver/Admin; "write" access only to Author/Admin. min_role/min_role_write
name which grant a server's tools require.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Which concrete roles satisfy a named grant. has_role(*roles) checks ANY membership.
READ_ROLES = ("Reader", "Author", "Approver", "Admin")
WRITE_ROLES = ("Author", "Admin")
_GRANTS = {"Reader": READ_ROLES, "Author": WRITE_ROLES}


@dataclass(frozen=True)
class McpServer:
    id: str                              # learn · azure · entra · azdo · github · m365
    label: str
    url: str                             # remote MCP endpoint
    auth: str                            # "public" | "obo" | "github_pat" | "oauth_passthrough"
    obo_scope: str | None = None         # downstream scope for OBO (internal path)
    read_tools: tuple[str, ...] = ()     # → never_require approval
    write_tools: tuple[str, ...] = ()    # → always_require (routed via our HITL on AG-UI)
    min_role: str = "Reader"             # grant required to see read tools
    min_role_write: str = "Author"       # grant required to see write tools
    enabled: bool = True


# NOTE on tool names: read_tools/write_tools are HAND-CURATED (governance decision, not
# server-trusted). The names below are the documented tool names per server; verify against
# each server's live tool list when wiring that server (the unclassified→write fail-closed
# default protects us if a name drifts). Learn's are confirmed (microsoft_docs_*).
SERVERS: tuple[McpServer, ...] = (
    McpServer(
        id="learn",
        label="Microsoft Learn",
        url="https://learn.microsoft.com/api/mcp",
        auth="public",
        read_tools=("microsoft_docs_search", "microsoft_docs_fetch"),
    ),
    McpServer(
        id="azure",
        label="Azure",
        url="https://<azure-mcp-endpoint>",  # TODO: confirm the Azure MCP remote URL when wiring
        auth="obo",
        obo_scope="https://management.azure.com/.default",
        read_tools=("azure_resource_list", "azure_cost_query", "azure_diagnostics"),
        write_tools=("azure_resource_deploy",),
    ),
    McpServer(
        id="entra",
        label="Microsoft Entra",
        url="https://<entra-mcp-endpoint>",  # TODO: confirm when wiring
        auth="obo",
        obo_scope="https://graph.microsoft.com/.default",
        read_tools=("entra_directory_query",),
        write_tools=("entra_directory_change",),
    ),
    McpServer(
        id="azdo",
        label="Azure DevOps",
        url="https://<azdo-mcp-endpoint>",  # TODO: confirm when wiring
        auth="obo",
        obo_scope="499b84ac-1321-427f-aa17-267ca6975798/.default",  # Azure DevOps resource
        read_tools=("azdo_workitem_query", "azdo_pipeline_list"),
        write_tools=("azdo_workitem_create",),
    ),
    McpServer(
        id="github",
        label="GitHub",
        url="https://api.githubcopilot.com/mcp/",
        auth="github_pat",
        read_tools=("github_repo_search", "github_issue_list"),
        write_tools=("github_issue_create",),
    ),
    McpServer(
        id="m365",
        label="Microsoft 365",
        url="https://<m365-mcp-endpoint>",  # TODO: confirm when wiring
        auth="oauth_passthrough",
        obo_scope="https://graph.microsoft.com/.default",
        read_tools=(),
        write_tools=(),
        enabled=False,  # no M365 in this tenant — see spec open question #1
    ),
)


def get_server(server_id: str) -> McpServer:
    for s in SERVERS:
        if s.id == server_id:
            return s
    raise KeyError(server_id)


def enabled_servers() -> tuple[McpServer, ...]:
    return tuple(s for s in SERVERS if s.enabled)


def classify_tool(server: McpServer, tool_name: str) -> str:
    """'read' | 'write'. Fail-closed: anything not explicitly a read is a write."""
    if tool_name in server.read_tools:
        return "read"
    return "write"


def _granted(roles: set[str], min_role: str) -> bool:
    """True if `roles` satisfies the named grant (READ_ROLES / WRITE_ROLES)."""
    return bool(set(_GRANTS[min_role]) & roles)


def visible_tools(server: McpServer, roles: set[str]) -> tuple[list[str], list[str]]:
    """(read_tools, write_tools) this caller may see, by role. The caller never sees a tool
    above their grant — and a no-role caller sees nothing (fail-closed)."""
    reads = list(server.read_tools) if _granted(roles, server.min_role) else []
    writes = list(server.write_tools) if _granted(roles, server.min_role_write) else []
    return reads, writes
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run python -m eval.mcp_registry_test`
Expected: PASS — all `✓`, final `✅ MCP registry logic holds.`

- [ ] **Step 6: Commit**

```bash
git add apps/backend/app/agents/mcp/__init__.py apps/backend/app/agents/mcp/registry.py apps/backend/eval/mcp_registry_test.py
git commit -m "feat(mcp): registry of Microsoft first-party MCP servers (data + role logic)"
```

---

## Chunk 2: The `platform` agent + Learn MCP end-to-end (infra-free)

Wires the *public, read-only* Learn server through a real `MCPStreamableHTTPTool` into a `platform` agent and registers it over AG-UI. This is the spec's "infra-free proof" — no OBO, no approval, no azd. Writes/OBO/approval are Chunk 4.

### Task 2: Tool builder — registry → `MCPStreamableHTTPTool`s (role-filtered)

**Files:**
- Create: `apps/backend/app/agents/mcp/tools.py`
- Modify: `apps/backend/app/core/settings.py`

- [ ] **Step 1: Add settings** — in `apps/backend/app/core/settings.py`, add to `Settings` (near the other feature flags):

```python
    # MCP integration (platform/ops domain). Learn is public; the rest are infra-gated.
    mcp_enabled: bool = False
    mcp_learn_url: str = "https://learn.microsoft.com/api/mcp"
```

- [ ] **Step 2: Write `tools.py`**

Create `apps/backend/app/agents/mcp/tools.py`:

```python
"""Build live framework MCP tools from the registry for the CURRENT request.

Internal path only (MCPStreamableHTTPTool). Per server, filter tools to the caller's role
(registry.visible_tools), then construct the tool with:
  - allowed_tools = the visible read + write tool names (so the model can't call hidden ones)
  - approval_mode = "never_require" — native MCP approval does NOT execute over AG-UI
    (agent-framework #3199), so write approval is handled by OUR HITL card in the workflow,
    not here. We still gate WRITE visibility by role above; a Reader simply never sees a write.
  - header_provider = a callable that injects the per-user OBO bearer for auth="obo" servers
    (lazy: evaluated at call time with the request's credential). Public servers get none.

GitHub (auth="github_pat") and hosted OAuth-passthrough are handled in later chunks; this
builder covers public + obo. Unknown auth → server skipped (fail-closed).
"""

from __future__ import annotations

from agent_framework import MCPStreamableHTTPTool

from app.agents.mcp.registry import McpServer, enabled_servers, visible_tools
from app.core.auth import credential_for_request, current_roles


def _obo_header_provider(scope: str):
    """A header_provider that mints a fresh OBO bearer for the signed-in user at call time."""
    def provider(_existing: dict) -> dict:
        token = credential_for_request().get_token(scope)
        return {"Authorization": f"Bearer {token.token}"}
    return provider


def _build_one(server: McpServer, roles: set[str]) -> MCPStreamableHTTPTool | None:
    reads, writes = visible_tools(server, roles)
    allowed = reads + writes
    if not allowed:
        return None  # caller sees no tools on this server
    kwargs = {
        "name": f"mcp_{server.id}",
        "url": server.url,
        "allowed_tools": allowed,
        "approval_mode": "never_require",  # see module docstring (HITL handles writes)
    }
    if server.auth == "obo" and server.obo_scope:
        kwargs["header_provider"] = _obo_header_provider(server.obo_scope)
    elif server.auth != "public":
        return None  # github_pat / oauth_passthrough handled elsewhere
    return MCPStreamableHTTPTool(**kwargs)


def build_mcp_tools() -> list[MCPStreamableHTTPTool]:
    """All MCP tools the current caller may use, across enabled servers."""
    roles = current_roles()
    tools = [_build_one(s, roles) for s in enabled_servers()]
    return [t for t in tools if t is not None]
```

- [ ] **Step 3: Quick import smoke check**

Run: `uv run python -c "from app.agents.mcp.tools import build_mcp_tools; print('ok')"`
Expected: `ok` (no import error). *(Behavior is exercised end-to-end in Task 4.)*

- [ ] **Step 4: Commit**

```bash
git add apps/backend/app/agents/mcp/tools.py apps/backend/app/core/settings.py
git commit -m "feat(mcp): build role-filtered MCPStreamableHTTPTools from the registry"
```

### Task 3: The `platform` agent + prompt

**Files:**
- Create: `apps/backend/app/agents/platform.py`
- Modify: `apps/backend/app/agents/prompts.py`

- [ ] **Step 1: Add the instructions** — in `apps/backend/app/agents/prompts.py`, append:

```python
PLATFORM_INSTRUCTIONS = """You are the engineering-platform concierge. You answer using the
connected Microsoft tools (Learn docs, and — when enabled — Azure, Entra, Azure DevOps, GitHub).
Prefer a tool over guessing. Ground factual claims in tool results and say which tool/source you
used. If a tool you'd need isn't available to this user, say so plainly rather than inventing an
answer. For any action that changes state (deploy, create issue, directory change), explain what
you would do and let the approval step handle it — never claim you performed a write."""
```

- [ ] **Step 2: Write `platform.py`** (mirrors `app/agents/selfwiki.py`)

Create `apps/backend/app/agents/platform.py`:

```python
"""Platform/ops domain — a TOOL-driven agent (not KB-grounded).

Unlike the grounded experts (cockpit/selfwiki), this agent's capability is the set of
Microsoft first-party MCP tools assembled per-request from app/agents/mcp/. Tools are
role-filtered (Reader sees reads, Author/Admin see writes) and, for OBO servers, run as the
signed-in user. The /platform endpoint requires sign-in; the per-request tool build reads the
caller's roles + OBO credential from the request context (set by the auth dependency).

APIs mirror app/agents/selfwiki.py (agent-framework 1.9.0).
"""

from __future__ import annotations

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient

from app.agents.mcp.tools import build_mcp_tools
from app.agents.prompts import PLATFORM_INSTRUCTIONS
from app.core.auth import credential_for_request
from app.core.settings import settings


def platform_configured() -> bool:
    return bool(settings.mcp_enabled and settings.foundry_project_endpoint)


def build_platform_agent() -> Agent:
    """A tool-driven concierge over the Microsoft first-party MCP servers."""
    client = FoundryChatClient(
        project_endpoint=settings.foundry_project_endpoint or None,
        model=settings.foundry_model,
        credential=credential_for_request(),
    )
    return client.as_agent(
        name="PlatformConcierge",
        description="Engineering-platform concierge over Microsoft first-party MCP tools.",
        instructions=PLATFORM_INSTRUCTIONS,
        tools=build_mcp_tools(),
    )
```

- [ ] **Step 3: Smoke check the import**

Run: `uv run python -c "from app.agents.platform import build_platform_agent, platform_configured; print('ok')"`
Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add apps/backend/app/agents/platform.py apps/backend/app/agents/prompts.py
git commit -m "feat(mcp): platform/ops agent (tool-driven over MCP servers)"
```

### Task 4: Learn MCP end-to-end proof (the infra-free gate)

A runnable test that builds the Learn tool and actually calls the live public Learn MCP through the agent, asserting a grounded, source-citing answer. No azd, no OBO.

**Files:**
- Create: `apps/backend/eval/mcp_learn_test.py`

- [ ] **Step 1: Write the end-to-end test**

Create `apps/backend/eval/mcp_learn_test.py`:

```python
"""End-to-end proof: the platform agent answers a Microsoft-docs question via the PUBLIC
Learn MCP server — no OBO, no azd. The spec's infra-free gate ("run it, don't claim it").

Needs only a Foundry model (FOUNDRY_PROJECT_ENDPOINT + DefaultAzureCredential) and outbound
HTTPS to learn.microsoft.com. Auth is OFF locally, so current_roles() degrades open and the
Learn read tools are visible.

    MCP_ENABLED=1 uv run python -m eval.mcp_learn_test
"""

from __future__ import annotations

import asyncio
import sys

from app.agents.platform import build_platform_agent, platform_configured


async def _run() -> int:
    if not platform_configured():
        print("✗ platform not configured (set MCP_ENABLED=1 and FOUNDRY_PROJECT_ENDPOINT).")
        return 1
    agent = build_platform_agent()
    reply = await agent.run(
        "Using the Microsoft Learn docs, what is Azure AI Foundry Agent Service? "
        "Cite the doc you used."
    )
    text = str(reply)
    print("---- agent reply ----")
    print(text[:800])
    print("---------------------")
    ok = len(text) > 0 and ("learn.microsoft.com" in text.lower() or "foundry" in text.lower())
    print(f"  {'✓' if ok else '✗'} grounded answer with a Learn reference")
    if not ok:
        print("\n❌ Learn MCP did not produce a grounded answer.")
        return 1
    print("\n✅ Learn MCP end-to-end: the platform agent answered from the docs.")
    return 0


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run it (requires a Foundry model + network)**

Run: `MCP_ENABLED=1 uv run python -m eval.mcp_learn_test`
Expected: PASS — prints a Learn-grounded answer and `✅ Learn MCP end-to-end`. *(If no Foundry endpoint is provisioned, this is the one gate that needs `azd up`'s model deployment; the registry/tool unit tests in Chunk 1 stay green regardless.)*

- [ ] **Step 3: Commit**

```bash
git add apps/backend/eval/mcp_learn_test.py
git commit -m "test(mcp): Learn MCP end-to-end proof (infra-free, public server)"
```

### Task 5: Register the `/platform` AG-UI endpoint

**Files:**
- Modify: `apps/backend/app/main.py`

- [ ] **Step 1: Add the endpoint registration** — in `apps/backend/app/main.py`, add the import near the other agent imports:

```python
from app.agents.platform import build_platform_agent, platform_configured
```

and, after the `selfwiki` block, add:

```python
# Fourth domain: the platform/ops concierge — tool-driven over the Microsoft first-party
# MCP servers (Learn public now; OBO servers as infra lands). Per-request factory so each
# run builds tools under the caller's roles + OBO credential.
if platform_configured():
    add_agent_framework_fastapi_endpoint(
        app,
        agent=build_platform_agent,  # factory: per-request roles/credential
        path="/platform",
        dependencies=auth_dependencies(),
    )
```

> NOTE: confirm whether `add_agent_framework_fastapi_endpoint` accepts a **callable factory** for `agent=` (the helpdesk workflow uses a per-request factory via `OrderedAgentFrameworkWorkflow(workflow_factory=...)`; the grounded domains pass a built agent). If it requires an already-built agent, wrap `build_platform_agent` the same way the helpdesk path wraps its factory so tools are rebuilt per request (the role/OBO filter MUST run per request, not once at boot). Adjust this step to match the verified signature — do not guess.

- [ ] **Step 2: Boot the backend and verify the route exists**

Run: `MCP_ENABLED=1 uv run uvicorn app.main:app --port 8000` then in another shell `curl -s localhost:8000/openapi.json | grep -o '/platform'`
Expected: `/platform` present (and the server boots without error).

- [ ] **Step 3: Commit**

```bash
git add apps/backend/app/main.py
git commit -m "feat(mcp): register /platform AG-UI endpoint (gated on mcp_enabled)"
```

---

## Chunk 3: Frontend wiring (the `tool` domain + resume bridge generalization)

Makes `/d/platform` reachable and registers its agent with the HITL resume bridge (so write approvals will work), generalizing the route so future interrupt-bearing domains are one registry entry.

### Task 6: Add the `platform` domain to the registry

**Files:**
- Modify: `apps/frontend/lib/domains.ts`

- [ ] **Step 1: Extend the union + add the entry** — in `apps/frontend/lib/domains.ts`:

Change:
```ts
export type DomainKind = "workflow" | "grounded";
```
to:
```ts
export type DomainKind = "workflow" | "grounded" | "tool";
```
and update the `kind` doc-comment to mention `"tool" = tool-driven (MCP) with HITL on writes`.

Add to the `DOMAINS` array:
```ts
  {
    id: "platform",
    icon: "🛠️",
    label: "Platform ops",
    kind: "tool",
    blurb:
      "Concierge de plataforma sobre as ferramentas Microsoft (Learn, Azure, Entra, DevOps, GitHub) — com aprovação humana antes de qualquer ação de escrita.",
    suggested: [
      "O que é o Azure AI Foundry Agent Service? (via Microsoft Learn)",
      "Liste os recursos do meu resource group.",
      "Quanto gastei em AI Search neste mês?",
    ],
    endpoint: "/platform",
  },
```

- [ ] **Step 2: Typecheck**

Run (from `apps/frontend/`): `npx tsc --noEmit`
Expected: no errors. *(The route change in Task 7 consumes the new kind; if tsc flags an exhaustiveness switch on `DomainKind`, that's expected until Task 7 — proceed.)*

- [ ] **Step 3: Commit**

```bash
git add apps/frontend/lib/domains.ts
git commit -m "feat(mcp): add platform 'tool' domain to the registry"
```

### Task 7: Generalize the copilotkit route to register interrupt-bearing domains

**Files:**
- Modify: `apps/frontend/app/api/copilotkit/[[...slug]]/route.ts`

- [ ] **Step 1: Extract the resume bridge + register tool/workflow domains from the registry**

In `apps/frontend/app/api/copilotkit/[[...slug]]/route.ts`, refactor so the `helpdesk` fetch transform becomes a reusable factory and any non-`grounded` domain is built from `DOMAINS` with it. Replace the bespoke `helpdesk` const + `groundedAgents` block with:

```ts
// Resume-format bridge (AG-UI `resume` array → agent-framework `{interrupts:[…]}` dict),
// needed by any domain with HITL interrupts (workflow + tool).
function withResumeBridge(url: string): HttpAgent {
  return new HttpAgent({
    url,
    fetch: async (u, requestInit) => {
      if (requestInit?.body && typeof requestInit.body === "string") {
        try {
          const body = JSON.parse(requestInit.body);
          if (Array.isArray(body.resume)) {
            body.resume = {
              interrupts: body.resume.map(
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                (r: any) => ({ id: r.interruptId ?? r.id, value: r.payload ?? r.value }),
              ),
            };
            requestInit = { ...requestInit, body: JSON.stringify(body) };
          }
        } catch {
          // leave the body untouched if it isn't JSON
        }
      }
      return fetch(u, requestInit);
    },
  });
}

const urlFor = (d: { id: string; endpoint: string }) =>
  process.env[`${d.id.toUpperCase()}_AGUI_URL`] ?? `http://localhost:8000${d.endpoint}`;

// Grounded domains are plain request→response. Interrupt-bearing domains (workflow + tool)
// get the resume bridge. Both come straight from the registry — adding a domain is one entry
// in lib/domains.ts (+ its backend agent), no per-domain wiring here.
const registryAgents = Object.fromEntries(
  DOMAINS.map((d) => [
    d.id,
    d.kind === "grounded"
      ? new HttpAgent({ url: urlFor(d) })
      : withResumeBridge(d.id === "helpdesk" ? AGUI_URL : urlFor(d)),
  ]),
);

const runtime = new CopilotRuntime({
  // helpdesk keeps its hosted twin; everything else (incl. platform) comes from the registry.
  agents: { ...registryAgents, "helpdesk-hosted": helpdeskHosted },
});
```

Keep the `AGUI_URL`, `HOSTED_AGUI_URL`, and `helpdeskHosted` consts as-is. Remove the now-unused standalone `helpdesk` const and the old `groundedAgents` block.

- [ ] **Step 2: Typecheck + lint**

Run (from `apps/frontend/`): `npx tsc --noEmit && npm run lint`
Expected: no errors.

- [ ] **Step 3: Manual smoke (with backend running)**

With `MCP_ENABLED=1` backend up and `npm run dev`: open `http://localhost:3000/d/platform`, send "O que é o Azure AI Foundry Agent Service?" → a Learn-grounded reply renders in the chat.
Expected: the platform domain appears in the sidebar and answers.

- [ ] **Step 4: Commit**

```bash
git add apps/frontend/app/api/copilotkit/[[...slug]]/route.ts
git commit -m "feat(mcp): register interrupt-bearing domains from the registry (shared resume bridge)"
```

---

## Chunk 4: Infra-gated follow-on (OBO servers, GitHub, writes+HITL, hosted, M365)

These need live Azure / external services, so they can't be TDD'd offline. Each is a self-contained follow-on; do them as the dependency lands. Keep the same registry/tool-builder seams — most of this is config + verifying real signatures, **not** new abstractions.

### Task 8: OBO servers (azure / entra / azdo) — read path
- Provision via `azd up`; grant admin consent for the Graph/ARM scopes (reuse `scripts/setup-app-roles.sh` patterns).
- Confirm each server's real remote MCP **URL** and **tool names** (replace the `TODO` URLs + verify `read_tools` against the live tool list). The unclassified→write fail-closed default covers drift.
- The `_obo_header_provider` already mints the per-user OBO bearer; verify the downstream scope is accepted by each server (azure `management.azure.com`, entra/m365 `graph`, azdo `499b84ac…`).
- Validate as the signed-in user (auth ON): a Reader gets read results trimmed to their own permissions; a no-role caller sees no tools.
- **Verify** `MCPStreamableHTTPTool.header_provider` is invoked per call (so the OBO token is fresh) — if the framework caches it, switch to per-request tool construction.

### Task 9: Write tools + HITL approval (the #3199 workaround)
- For write tools (`azure_resource_deploy`, `azdo_workitem_create`, `entra_directory_change`, `github_issue_create`): route execution through the **existing HITL approval card** (the `create_ticket`/`request_info` interrupt mechanism), NOT the framework's `approval_mode` (broken over AG-UI, #3199).
- Re-check `has_role(server.min_role_write)` immediately before the write executes (defense in depth — don't rely on tool-list filtering alone).
- The frontend resume bridge (Task 7) is already in place, so the approve/reject round-trip works for `kind: "tool"`.
- Test: as an Author, ask for a write → approval card appears → approve → tool runs; reject → no write. As a Reader, the write tool isn't even offered.

### Task 10: GitHub MCP (PAT path)
- `auth="github_pat"`: extend the tool builder to handle `github_pat` — inject `Authorization: Bearer <PAT>` from a connection/secret (MVP: a shared PAT via settings; per-user GitHub OAuth later, spec open question #2).
- Verify against `https://api.githubcopilot.com/mcp/` tool names.

### Task 11: Hosted mirror (Foundry OAuth passthrough)
- **Blocked on** the custom-OAuth app registration (spec open question #4) — design that first.
- Build the hosted tools via `FoundryChatClient.get_mcp_tool(name, url, approval_mode, headers, allowed_tools)` / a Foundry **toolbox**, fed by the SAME registry; auth via `project_connection_id` (OAuth identity passthrough), NOT OBO-in-header (hosted-OBO bug azure-sdk #46696).
- Hosted uses native `require_approval=always` on writes (the AG-UI bug doesn't apply to the hosted path).
- Wire as the hosted twin alongside `/platform` (mirror the `helpdesk-hosted` pattern) and surface via the existing live-vs-hosted toggle.

### Task 12: M365 (deferred)
- Keep `enabled=False` until M365 is enabled in the tenant (M365 Developer Program); Agent 365 MCP servers are Frontier-tenant-gated (spec open question #1). When available: flip `enabled`, confirm URL + tools, validate via OBO/passthrough Graph scope.

---

## Done criteria

- **Chunk 1** (infra-free): `uv run python -m eval.mcp_registry_test` is green.
- **Chunk 2** (needs a Foundry model): `MCP_ENABLED=1 uv run python -m eval.mcp_learn_test` is green — a real, Learn-grounded answer.
- **Chunk 3** (frontend): `/d/platform` answers in the UI; `tsc`/lint clean.
- **Chunk 4**: each follow-on validated against its live service as the dependency lands, with writes gated by role + HITL.
