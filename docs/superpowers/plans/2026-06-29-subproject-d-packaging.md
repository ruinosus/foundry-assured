# Sub-project D-packaging Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish D — deploy the platform hosted agent for real (Invocations + Foundry Toolbox per-tenant + write-approval HITL), author the dedicated-stamp marketplace IaC (Managed App + Lighthouse), and close the small deferred code (tier→domains, PerRequest collapse, #3199 live verify).

**Architecture:** One spec, three independently-testable phases, each split into an infra-free deliverable (authored + structurally validated now) and an infra-gated validation (deployed Foundry / Partner Center / customer tenants). Self-hosted stays byte-identical (mode-gated). Per [the D-packaging design](../specs/2026-06-29-subproject-d-packaging-design.md), [ADR-011](../../adr/ADR-011-hosted-per-tenant-foundry-toolbox-passthrough.md), [ADR-002](../../adr/ADR-002-dedicated-stamp-managed-app-lighthouse.md), [ADR-010](../../adr/ADR-010-per-tenant-domain-entitlement.md).

**Tech Stack:** Python 3.12 / `agent-framework` + `agent-framework-foundry-hosting` (`InvocationsHostServer`) / `azure-ai-projects` (Foundry, Toolbox) / FastAPI; Bicep → ARM JSON (Managed App `mainTemplate.json` + `createUiDefinition.json`), Azure Lighthouse (`Microsoft.ManagedServices`); azd (`host: azure.ai.agent`). Tests: runnable `def main() -> int` in `apps/backend/eval/` via `uv run python -m eval.<name>` from `apps/backend/` — **NO pytest**.

**Branch:** `feature/saas-d-packaging` (created, stacked on D-runtime).

**Project rule #1 (inviolable):** never invent SDK signatures. **Phase 1 begins with a step-0 verification task that GATES all Phase 1 coding.**

---

## File Structure

**Phase 1 — Hosted (`apps/`, `apps/backend/`):**
- `apps/hosted-platform/{Dockerfile,agent.yaml,main.py,requirements.txt}` — new container; mirrors `apps/hosted-agent/` **layout only**. `main.py` wraps `build_platform_agent()` in `InvocationsHostServer` (NOT the single-identity Responses stripping). Serves `POST /invocations` on 8088.
- `azure.yaml` — 3rd `host: azure.ai.agent` service `platform-concierge`.
- `apps/backend/app/services/hosted.py` — real `stream_platform_agui` (AG-UI passthrough proxy; replaces the `NotImplementedError` skeleton).
- `docs/superpowers/notes/d-packaging-verifications.md` — step-0 findings.

**Phase 2 — Stamp IaC (`infra/`):**
- `infra/managed-app/{managedApp.bicep, mainTemplate.json (compiled), createUiDefinition.json, build.sh}` — Bicep composes `resources.bicep` + `containerapps.bicep` at the managed-RG scope.
- `infra/lighthouse/{lighthouse.bicep or template.json, parameters.json}` — `Microsoft.ManagedServices` delegation.
- `docs/D-PACKAGING-RUNBOOK.md` — marketplace publish + Lighthouse onboarding (infra-gated).

**Phase 3 — Leftovers (`apps/backend/`):**
- `app/core/tenant.py` — `TIER_DOMAINS` map.
- `app/api/tenant.py` — `OnboardBody` + `onboard()` seeds `enabled_domains` from tier.
- `app/agents/per_request.py` (name/description override) & `app/agents/platform.py` (delete `PerRequestPlatformAgent`, express via `PerRequestAgent`); `app/main.py` import update.
- `app/agents/mcp/` — conditional `RequestInfoEvent` middleware (only if #3199 live-check fails).
- `apps/backend/eval/` — `tier_domains_test`, `per_request_override_test`, `hosted_platform_smoke_test` (+ infra-gated `platform_hosted_e2e` expanded).

---

## Chunk 1: Phase 1 — Hosted platform agent (full parity)

### Task 0: STEP-0 verification (GATES all Phase 1 coding — rule #1)

No production code. Produces `docs/superpowers/notes/d-packaging-verifications.md`. Nothing in Tasks 1–3 may be coded until this is recorded.

- [ ] **Step 1: Verify `InvocationsHostServer`**

```bash
cd apps/backend
uv run python - <<'PY'
import importlib
try:
    m = importlib.import_module("agent_framework_foundry_hosting")
    print("module attrs:", [a for a in dir(m) if "Host" in a or "Server" in a or "Invoc" in a])
    import inspect
    for name in ("InvocationsHostServer", "ResponsesHostServer"):
        cls = getattr(m, name, None)
        print(name, "->", None if cls is None else inspect.signature(cls.__init__))
except Exception as e:
    print("import failed:", type(e).__name__, e)
PY
```
Record: does `InvocationsHostServer` exist? Its constructor signature? Does it wrap a `SupportsAgentRun`/agent like `ResponsesHostServer(workflow_agent)` does (`apps/hosted-agent/main.py:107`)? **If it doesn't exist offline**, record that and treat the container's host-server line as infra-gated (the deployed image installs it) — but DO check the installed version first.

- [ ] **Step 2: Verify the platform agent drops in + the Toolbox/passthrough surface**

Confirm `build_platform_agent()` (`app/agents/platform.py:28`) returns an object the host server can wrap (it returns `client.as_agent(...)` — an `Agent`). Check whether MCP tools for the hosted path come from a **Foundry Toolbox** config vs the live `build_mcp_tools()`: inspect `app/agents/mcp/tools.py` for `build_hosted_from_connections` (C) and check `azure-ai-projects` for a Toolbox/MCP-connection + OAuth-passthrough API:
```bash
uv run python -c "import azure.ai.projects as p, importlib.metadata as m; print(m.version('azure-ai-projects'))"
uv run python - <<'PY'
import importlib, pkgutil
m = importlib.import_module("azure.ai.projects")
print([n for _,n,_ in pkgutil.walk_packages(m.__path__, m.__name__+'.') if any(k in n.lower() for k in ('tool','mcp','connect'))][:40])
PY
```
Record the Toolbox config surface + how OAuth identity passthrough is declared per connection (cross-check the Toolbox / mcp-authentication Learn docs). **If not determinable offline**, record it as infra-gated and have the container reference the Toolbox by name/env (configured at deploy, in the runbook), not hand-rolled in code.

- [ ] **Step 3: Verify the bridge (client) side**

The `stream_platform_agui` bridge POSTs to the deployed agent's Invocations endpoint and relays SSE. Check whether `azure-ai-projects` exposes a first-party client for invoking a hosted agent's `/protocols/invocations` (vs a raw authenticated `httpx` POST). The existing Responses bridge uses `project.get_openai_client(...).responses.create(...)` (`app/services/hosted.py`); there is likely **no** OpenAI-style client for Invocations (it's raw SSE). Record: first-party client OR raw `httpx`/`aiohttp` POST with the request bearer token. Note: the response bytes are **AG-UI** (flow untouched), so the relay is a passthrough — no envelope parsing.

- [ ] **Step 4: Write + commit the note**

`docs/superpowers/notes/d-packaging-verifications.md` (mirror `d-verifications.md`'s Unknown | Finding | Impact table): the `InvocationsHostServer` signature (or infra-gated), the Toolbox/passthrough config surface (or infra-gated + runbook), the bridge client choice. For each, state what Tasks 1–3 may implement now vs fence as `TODO(infra-gated)`.

```bash
cd /Users/jefferson.barnabe/projects/foundry-helpdesk
git add docs/superpowers/notes/d-packaging-verifications.md
git commit -m "docs(D-packaging): Task 0 — verify InvocationsHostServer + Toolbox passthrough + bridge client"
```

---

### Task 1: `apps/hosted-platform/` container (Invocations, full-parity agent)

**Files:**
- Create: `apps/hosted-platform/{Dockerfile,agent.yaml,main.py,requirements.txt}`
- Test: `apps/backend/eval/hosted_platform_smoke_test.py`

> Implement per Task 0's findings. The host-server line follows the verified `InvocationsHostServer` signature; if Task 0 found it isn't importable offline, keep the `main.py` structure but expect the smoke test to assert import-up-to-the-host-server (or mark that line infra-gated). Do NOT copy `hosted-agent/main.py`'s workflow-rebuild/single-identity stripping — only its file scaffold.

- [ ] **Step 1: Write the failing smoke test** `apps/backend/eval/hosted_platform_smoke_test.py`:

```python
"""apps/hosted-platform is well-formed: agent.yaml declares the Invocations protocol, and
main.py is importable (its module-level wiring doesn't crash). Infra-free — does NOT start the
host server or deploy.

    uv run python -m eval.hosted_platform_smoke_test
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml  # pyyaml ships with the backend deps


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {name}")
        if not cond:
            failures.append(name)

    root = Path(__file__).resolve().parents[2] / "hosted-platform"
    check("hosted-platform/ exists", root.is_dir())
    for f in ("Dockerfile", "agent.yaml", "main.py", "requirements.txt"):
        check(f"{f} present", (root / f).is_file())

    spec = yaml.safe_load((root / "agent.yaml").read_text())
    check("agent.yaml kind: hosted", spec.get("kind") == "hosted")
    check("agent.yaml name: platform-concierge", spec.get("name") == "platform-concierge")
    protocols = [p.get("protocol") for p in (spec.get("protocols") or [])]
    check("agent.yaml declares the invocations protocol", "invocations" in protocols)

    if failures:
        print(f"\n❌ {len(failures)} assertion(s) failed.")
        return 1
    print("\n✅ hosted-platform scaffold well-formed (Invocations).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run it, expect FAIL** (`apps/hosted-platform` doesn't exist).
`cd apps/backend && uv run python -m eval.hosted_platform_smoke_test`

- [ ] **Step 3: Create the scaffold.**

`apps/hosted-platform/agent.yaml` (mirror `hosted-agent/agent.yaml`, but Invocations + platform env):
```yaml
kind: hosted
name: platform-concierge
protocols:
  - protocol: invocations
    version: 1.0.0
resources:
  cpu: "0.5"
  memory: 1Gi
environment_variables:
  # FOUNDRY_PROJECT_ENDPOINT + APPLICATIONINSIGHTS_CONNECTION_STRING injected by the platform.
  - name: AZURE_AI_MODEL_DEPLOYMENT_NAME
    value: ${FOUNDRY_MODEL}
  # The Foundry Toolbox the agent resolves its MCP tools through (ADR-011). Name/ref set at deploy.
  - name: FOUNDRY_TOOLBOX_NAME
    value: ${FOUNDRY_TOOLBOX_NAME}
```

`apps/hosted-platform/Dockerfile` — copy `hosted-agent/Dockerfile` verbatim (same `python:3.12-slim`, `EXPOSE 8088`, `CMD ["python","main.py"]`).

`apps/hosted-platform/requirements.txt`:
```
agent-framework
agent-framework-foundry-hosting
python-dotenv
```

`apps/hosted-platform/main.py` — wraps the platform agent in `InvocationsHostServer` (signature per Task 0). Skeleton shape (adjust imports/host-server to Task 0's findings):
```python
"""Hosted platform agent (D-packaging Phase 1).

The platform/ops concierge as a Foundry HOSTED agent over the **Invocations** protocol —
so the AG-UI event stream (including the write-approval HITL interrupt) flows through Foundry
UNTOUCHED (ADR-011). Unlike hosted-agent/hosted-cockpit (single-identity Responses variants),
this serves the SAME tool-driven AG-UI agent as the live /platform, with per-tenant tools +
identity brokered by the Foundry Toolbox (OAuth identity passthrough) — the container holds no
credentials. Tools are configured on the Toolbox at deploy, not built in-container.
"""

import asyncio
import os

from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import InvocationsHostServer  # per Task 0
from azure.identity import DefaultAzureCredential

from prompts import PLATFORM_INSTRUCTIONS  # see prompt-vendoring note below


async def main() -> None:
    credential = DefaultAzureCredential()
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=credential,
    )
    # Tools resolve through the Foundry Toolbox (ADR-011) — referenced by name/env, configured
    # at deploy (runbook). The agent definition holds Toolbox references, never a secret.
    agent = client.as_agent(
        name="PlatformConcierge",
        instructions=PLATFORM_INSTRUCTIONS,
        # tools: from the Foundry Toolbox MCP endpoint (per Task 0 — TODO(infra-gated) if the
        # config surface isn't determinable offline; reference FOUNDRY_TOOLBOX_NAME).
    )
    server = InvocationsHostServer(agent)
    await server.run_async()


if __name__ == "__main__":
    asyncio.run(main())
```
> The exact tool-wiring + host-server call MUST match Task 0. If Task 0 fenced the Toolbox surface as infra-gated, leave a precise `TODO(infra-gated)` and reference the Toolbox by env — do not hand-roll credential code (ADR-011/rule #1).
>
> **Prompt vendoring (the container has no backend on its path):** `PLATFORM_INSTRUCTIONS` lives in the backend at `app/agents/prompts.py` — NOT importable from the container. Either **inline** the platform instructions string in `hosted-platform/main.py` (as `hosted-agent/main.py` does for its instructions), or **vendor** a small `apps/hosted-platform/prompts.py` copying just `PLATFORM_INSTRUCTIONS`. Inlining is simplest; pick one and the `from prompts import …` line resolves.

- [ ] **Step 4: Run the smoke test, expect PASS** (`✅ hosted-platform scaffold well-formed (Invocations).`).
> If Task 0 found `InvocationsHostServer` isn't importable in the backend venv (it's a hosted-image dep), the smoke test still passes — it does NOT import `main.py`; it only checks file presence + parses `agent.yaml`. (Importing `main.py` here would require the hosting package; keep the test to scaffold+yaml so it stays infra-free.)

- [ ] **Step 5: Commit**
```bash
cd /Users/jefferson.barnabe/projects/foundry-helpdesk
git add apps/hosted-platform apps/backend/eval/hosted_platform_smoke_test.py
git commit -m "feat(D-packaging): apps/hosted-platform container (Invocations, full-parity platform agent)"
```

---

### Task 2: `azure.yaml` — 3rd hosted service

**Files:** Modify `azure.yaml` (the `services:` map).

- [ ] **Step 1: Add the service** (mirror the existing `helpdesk-concierge`/`cockpit-expert` entries):
```yaml
    platform-concierge:
        project: apps/hosted-platform
        host: azure.ai.agent
        language: docker
        docker:
            remoteBuild: true
        config:
            container:
                resources:
                    cpu: "0.5"
                    memory: 1Gi
            startupCommand: python main.py
```

- [ ] **Step 2: Validate YAML parses**
```bash
cd /Users/jefferson.barnabe/projects/foundry-helpdesk
python -c "import yaml; d=yaml.safe_load(open('azure.yaml')); assert 'platform-concierge' in d['services']; print('ok:', list(d['services']))"
```
Expected: `ok: [...'platform-concierge']`.

- [ ] **Step 3: Commit**
```bash
git add azure.yaml
git commit -m "feat(D-packaging): register platform-concierge hosted agent in azure.yaml"
```

---

### Task 3: real `stream_platform_agui` (AG-UI passthrough proxy)

**Files:** Modify `apps/backend/app/services/hosted.py` (replace the skeleton's `NotImplementedError` body). Test: the existing `apps/backend/eval/platform_hosted_bridge_test.py` stays green; expand `apps/backend/eval/platform_hosted_e2e_test.py` (infra-gated).

> Implement the relay per Task 0 Step 3 (first-party invocations client vs raw authenticated `httpx` POST). The response bytes are AG-UI — relay them through; do NOT parse/re-encode an envelope. The no-endpoint clean-error path stays exactly as today.

- [ ] **Step 1: Confirm the infra-free contract still holds (no new test needed; the bridge test guards it).**
Read the current `stream_platform_agui` (`app/services/hosted.py`). The infra-free behavior: no `foundry_project_endpoint` → `_platform_invocations_url()` returns `""` → clean `RunErrorEvent`. This MUST remain (the bridge test asserts a terminal `RUN_ERROR` offline).

- [ ] **Step 2: Replace the `NotImplementedError` with the real relay.** Inside the `try`, after `url = _platform_invocations_url()` and the empty-url guard, POST the AG-UI run to `url` with the request bearer token and relay the SSE. Shape (adapt the client to Task 0):
```python
        # Real path: POST the AG-UI run to the deployed agent's Invocations endpoint and relay
        # the SSE. The bytes are already AG-UI (flow untouched, ADR-011) — pass them through.
        import httpx  # or the first-party invocations client per Task 0
        from app.core.auth import credential_for_request

        token = credential_for_request().get_token("https://ai.azure.com/.default").token  # scope per Task 0
        headers = {"Authorization": f"Bearer {token}", "Accept": "text/event-stream"}
        async with httpx.AsyncClient(timeout=None) as http:
            async with http.stream("POST", url, json=body, headers=headers) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line:                      # AG-UI SSE lines, untouched
                        yield line + "\n"
```
> If Task 0 found a first-party invocations client, use it instead of raw `httpx`. The auth scope + the exact POST body shape come from Task 0; if any piece isn't verifiable offline, fence it `TODO(infra-gated)` and keep the offline clean-error path. The `except Exception` already converts failures (incl. an unreachable agent) to a clean `RunErrorEvent`.

- [ ] **Step 3: Run the bridge test, expect PASS (still green offline)**
`cd apps/backend && uv run python -m eval.platform_hosted_bridge_test` — offline (no endpoint) still yields the terminal `RUN_ERROR`. (Add `httpx` to backend deps only if not already present: `uv add httpx` — check `pyproject.toml` first.)

- [ ] **Step 4: Expand the infra-gated E2E** `apps/backend/eval/platform_hosted_e2e_test.py` — keep the skip-clean gate (empty `foundry_project_endpoint` → `⏭ skipped`, `return 0`). In the endpoint-present branch, drive `stream_platform_agui` against the live Invocations endpoint and assert a non-error terminal + (when a write tool is requested) the approval interrupt surfaces. **Namespace note:** patch `app.services.hosted.tenant_config` (the importing namespace) to point at a configured endpoint. This stays infra-gated (real deployed agent + Toolbox).

- [ ] **Step 5: Commit**
```bash
cd /Users/jefferson.barnabe/projects/foundry-helpdesk
git add apps/backend/app/services/hosted.py apps/backend/eval/platform_hosted_e2e_test.py apps/backend/pyproject.toml apps/backend/uv.lock
git commit -m "feat(D-packaging): real stream_platform_agui — AG-UI passthrough to the Invocations endpoint"
```

---

## Chunk 2: Phase 2 — Dedicated stamp (Managed App + Lighthouse IaC)

> All structurally validated offline. Marketplace publish + real-tenant delegation are the runbook (infra-gated) — never a fabricated pass.

### Task 4: Managed Application package

**Files:**
- Create: `infra/managed-app/managedApp.bicep`, `infra/managed-app/createUiDefinition.json`, `infra/managed-app/build.sh`
- Generated: `infra/managed-app/mainTemplate.json` (from `bicep build`)

- [ ] **Step 1: Author `infra/managed-app/managedApp.bicep`** — resource-group-scoped (managed apps deploy into the platform-provided managed RG; NO `resourceGroups` resource, unlike `infra/main.bicep`). Compose the existing modules:
```bicep
// Managed Application mainTemplate source. Deploys the dedicated control plane into the
// customer's managed resource group. Composes the same infra/ modules as the azd path
// (resources.bicep + containerapps.bicep), re-parameterized for the customer subscription.
// Compiled to mainTemplate.json via build.sh (ADR-002 implementation note).
targetScope = 'resourceGroup'

@description('Primary location (defaults to the managed resource group location).')
param location string = resourceGroup().location

@description('Model deployment name surfaced to the app as FOUNDRY_MODEL.')
param modelDeploymentName string = 'gpt-5-mini'

@description('Entra tenant for backend OBO.')
param entraTenantId string = ''
@description('Backend API app client id for OBO.')
param entraApiClientId string = ''
@secure()
@description('Backend API app client secret for OBO.')
param entraApiClientSecret string = ''

var resourceToken = toLower(uniqueString(resourceGroup().id, location))
var tags = { solution: 'foundry-assured-dedicated-stamp' }

module resources '../resources.bicep' = {
  name: 'resources'
  params: {
    location: location
    tags: tags
    resourceToken: resourceToken
    principalId: ''          // dedicated stamp: the publisher operates; no deploying-user data-plane grant
    modelDeploymentName: modelDeploymentName
    searchLocation: location
  }
}

module apps '../containerapps.bicep' = {
  name: 'containerapps'
  params: {
    location: location
    tags: tags
    resourceToken: resourceToken
    registryName: resources.outputs.AZURE_CONTAINER_REGISTRY_NAME
    appIdentityId: resources.outputs.APP_IDENTITY_ID
    appIdentityClientId: resources.outputs.APP_IDENTITY_CLIENT_ID
    foundryProjectEndpoint: resources.outputs.FOUNDRY_PROJECT_ENDPOINT
    foundryModel: resources.outputs.FOUNDRY_MODEL
    azureSearchEndpoint: resources.outputs.AZURE_SEARCH_ENDPOINT
    azureSearchKnowledgeBase: resources.outputs.AZURE_SEARCH_KNOWLEDGE_BASE
    storageAccountName: resources.outputs.AZURE_STORAGE_ACCOUNT
    fileShareName: resources.outputs.AZURE_FILE_SHARE
    entraTenantId: entraTenantId
    entraApiClientId: entraApiClientId
    entraApiClientSecret: entraApiClientSecret
  }
}

output BACKEND_URL string = apps.outputs.BACKEND_URL
output WEB_URL string = apps.outputs.WEB_URL
```
> Verify the `resources.bicep` / `containerapps.bicep` param lists match (read both); if a param is required that the managed path can't supply, add a sensible default in the module call or note it. Do NOT modify the shared modules in a way that breaks the azd path — if a change is needed, make it additive/defaulted.

- [ ] **Step 2: Author `createUiDefinition.json`** — minimal valid createUiDefinition (handler `Microsoft.Azure.CreateUIDef`) exposing the parameters (`modelDeploymentName`, the Entra OBO params) and outputs mapping to the template params. Use the documented schema skeleton; keep it minimal.

- [ ] **Step 3: Author `build.sh`** — compiles + packages:
```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
az bicep build --file managedApp.bicep --outfile mainTemplate.json
# Marketplace package: mainTemplate.json + createUiDefinition.json at the ZIP root.
zip -j managed-app.zip mainTemplate.json createUiDefinition.json
echo "built managed-app.zip"
```

- [ ] **Step 4: Validate offline** — `bicep build` compiles; ARM-TTK if available:
```bash
cd infra/managed-app && az bicep build --file managedApp.bicep --outfile mainTemplate.json && echo "bicep build OK"
# ARM-TTK (if pwsh + the toolkit are installed); else this is the documented manual gate:
# pwsh -c "Test-AzTemplate -TemplatePath ."
```
Expected: `mainTemplate.json` generated, `bicep build OK`. If `az`/bicep isn't installed in the env, record that Phase 2 validation is the documented gate (the runbook) and that the Bicep is authored but compiled where the toolchain exists.
> **Heads-up (pre-existing):** `resources.bicep` and `containerapps.bicep` each declare a `logAnalytics` resource named `log-helpdesk-${resourceToken}`. In the azd path they're in separate RG-scoped module deployments so it's fine; if composing them under `managedApp.bicep` makes `bicep build` flag a duplicate resource-name at RG scope, that's the cause — dedupe by having one module own Log Analytics and pass its id to the other (additive change; don't break the azd path).

- [ ] **Step 5: Commit**
```bash
cd /Users/jefferson.barnabe/projects/foundry-helpdesk
git add infra/managed-app
git commit -m "feat(D-packaging): Managed Application package (Bicep composing infra modules -> mainTemplate + createUiDefinition)"
```

---

### Task 5: Lighthouse delegation template

**Files:** Create `infra/lighthouse/lighthouse.bicep`, `infra/lighthouse/parameters.json`.

- [ ] **Step 1: Author the delegation** — a `Microsoft.ManagedServices/registrationDefinitions` + `registrationAssignments`, least-privilege (specific built-in role IDs, e.g. Reader + a scoped operator role), parameterized by the managing tenant id + principal/group. Use the documented Lighthouse template schema (ADR-002's sources). Keep authorizations least-privilege + a `principalIdDisplayName`.

- [ ] **Step 2: Validate offline** — `az bicep build --file lighthouse.bicep` compiles (or `az deployment ... validate` where a sub is available; else documented). Expected: compiles clean.

- [ ] **Step 3: Commit**
```bash
git add infra/lighthouse
git commit -m "feat(D-packaging): Azure Lighthouse delegation template (least-privilege, revocable)"
```

---

### Task 6: Publish + onboarding runbook

**Files:** Create `docs/D-PACKAGING-RUNBOOK.md`.

- [ ] **Step 1: Write the runbook** — the infra-gated steps, honestly labeled: (a) Managed App → Partner Center offer creation, upload `managed-app.zip`, plan config (publisher management, Complete vs Incremental), publish; (b) customer deploys the Managed App into their subscription; (c) Lighthouse → customer deploys `infra/lighthouse` to delegate scopes to our managing tenant (revocable); (d) deploy the `platform-concierge` hosted agent (`azd deploy`) + provision the Foundry Toolbox (ADR-011) + wire `FOUNDRY_TOOLBOX_NAME`. Mark each as requiring a Partner Center account / customer subscription / deployed Foundry (NOT runnable in CI).

- [ ] **Step 2: Commit**
```bash
git add docs/D-PACKAGING-RUNBOOK.md
git commit -m "docs(D-packaging): marketplace publish + Lighthouse + hosted-deploy runbook (infra-gated)"
```

---

## Chunk 3: Phase 3 — Leftovers

### Task 7: tier→domains map + `OnboardBody`

**Files:** Modify `app/core/tenant.py` (`TIER_DOMAINS`), `app/api/tenant.py` (`OnboardBody` + `onboard` seeds from tier). Test: `apps/backend/eval/tier_domains_test.py`.

- [ ] **Step 1: Write the failing test** `apps/backend/eval/tier_domains_test.py`:
```python
"""TIER_DOMAINS seeds onboarding entitlement from the tenant's tier; unknown/unset tier → all
domains (non-breaking); the request-time gate stays fail-closed regardless. Infra-free.

    uv run python -m eval.tier_domains_test
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

from app.core import auth as _auth
import app.api.tenant as tapi
from app.core.tenant import DOMAIN_IDS, TIER_DOMAINS, domains_for_tier
from app.core.tenant_store import InMemoryTenantStore


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {name}")
        if not cond:
            failures.append(name)

    check("shared tier → all domains", domains_for_tier("shared") == DOMAIN_IDS)
    check("unknown tier → all domains (non-breaking)", domains_for_tier("mystery") == DOMAIN_IDS)
    check("None tier → all domains", domains_for_tier(None) == DOMAIN_IDS)
    # a restricted tier, if defined, is a strict subset of the catalog
    for tier, doms in TIER_DOMAINS.items():
        check(f"tier '{tier}' ⊆ DOMAIN_IDS", set(doms) <= set(DOMAIN_IDS))

    # onboard seeds from the tier passed in the body
    store = InMemoryTenantStore()
    _auth._tenant_store = store
    tapi.onboard(tapi.OnboardBody(tier="shared"), SimpleNamespace(tid="t-1"))
    check("onboard seeds enabled_domains from tier", store.get("t-1").enabled_domains == domains_for_tier("shared"))
    _auth._tenant_store = None

    if failures:
        print(f"\n❌ {len(failures)} assertion(s) failed.")
        return 1
    print("\n✅ tier→domains seeding holds (unknown→all, gate stays fail-closed).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run it, expect FAIL** (`ImportError: TIER_DOMAINS` / `domains_for_tier`).

- [ ] **Step 3: Implement.** `app/core/tenant.py` (after `DOMAIN_IDS`):
```python
# Per-tier domain entitlement (ADR-010 Open Q#3). Unknown/unset tier → all domains (non-breaking;
# the request-time require_domain gate stays fail-closed regardless of the seed).
TIER_DOMAINS: dict[str, tuple[str, ...]] = {
    "shared": DOMAIN_IDS,
    # example restricted tier (no consumer yet; the hook ADR-010 anticipated):
    "starter": ("helpdesk", "selfwiki"),
}


def domains_for_tier(tier: str | None) -> tuple[str, ...]:
    return TIER_DOMAINS.get(tier or "", DOMAIN_IDS)
```
`app/api/tenant.py` — add the body model + thread it through `onboard()`. Current signature is `def onboard(user: User = Depends(onboarding_guard))` with `enabled_domains=DOMAIN_IDS`. New:
```python
from app.core.tenant import TenantConfig, current_tenant_id, DOMAIN_IDS, domains_for_tier

class OnboardBody(BaseModel):
    tier: str | None = None

@router.post("/onboard")
def onboard(body: OnboardBody = OnboardBody(), user: User = Depends(onboarding_guard)):
    store = _store()
    tid = getattr(user, "tid", None)
    if store.get(tid) is None:
        tier = body.tier or "shared"
        store.put(TenantRecord(tid=tid, name=tid, tier=tier, status="active",
                               data_plane=TenantConfig(), enabled_domains=domains_for_tier(tier)))
    return {"onboarded": True}
```
> Verify FastAPI accepts a defaulted Pydantic body + a `Depends` param together (it does — body params and dependencies coexist). The frontend `Connections.tsx` onboard POST sends no body today; a defaulted `OnboardBody()` keeps that working (tier→ "shared" → all domains, identical to today).

- [ ] **Step 4: Run the test, expect PASS.**

- [ ] **Step 5: Run existing tenant tests** (`tenant_e2e_test`, `onboarding_guard_test`, `domains_api_test`) — confirm the onboard change didn't break them; update only an onboarded-record-shape assertion if one exists.

- [ ] **Step 6: Commit**
```bash
cd /Users/jefferson.barnabe/projects/foundry-helpdesk
git add apps/backend/app/core/tenant.py apps/backend/app/api/tenant.py apps/backend/eval/tier_domains_test.py
git commit -m "feat(D-packaging): tier→domains entitlement map + OnboardBody (closes ADR-010 Open Q#3)"
```

---

### Task 8: collapse `PerRequestPlatformAgent` into `PerRequestAgent`

**Files:** Modify `app/agents/per_request.py` (optional `name`/`description` overrides), `app/agents/platform.py` (delete the class; export a proxy via the generic), `app/main.py` (the platform-endpoint reference). Test: `apps/backend/eval/per_request_override_test.py`.

- [ ] **Step 1: Write the failing test** `apps/backend/eval/per_request_override_test.py`:
```python
"""PerRequestAgent accepts optional name/description overrides; the platform proxy uses them and
still satisfies SupportsAgentRun. Infra-free.

    uv run python -m eval.per_request_override_test
"""

from __future__ import annotations

import sys

from agent_framework import SupportsAgentRun
from app.agents.per_request import PerRequestAgent


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {name}")
        if not cond:
            failures.append(name)

    a = PerRequestAgent("platform", lambda: None, name="PlatformConcierge", description="desc")
    check("name override applied", a.name == "PlatformConcierge")
    check("description override applied", a.description == "desc")
    check("id is the agent_id", a.id == "platform")
    check("default name falls back to id", PerRequestAgent("cockpit", lambda: None).name == "cockpit")
    check("isinstance SupportsAgentRun", isinstance(a, SupportsAgentRun))

    # the platform module exposes a proxy instance built from the generic class
    from app.agents.platform import platform_agent_proxy  # new export
    check("platform proxy is SupportsAgentRun", isinstance(platform_agent_proxy, SupportsAgentRun))
    check("platform proxy keeps its name", platform_agent_proxy.name == "PlatformConcierge")

    if failures:
        print(f"\n❌ {len(failures)} assertion(s) failed.")
        return 1
    print("\n✅ PerRequestAgent override + platform proxy collapse holds.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run it, expect FAIL** (`PerRequestAgent` has no `name`/`description` kwargs; `platform_agent_proxy` doesn't exist).

- [ ] **Step 3: Implement.** `app/agents/per_request.py` — add optional overrides:
```python
    def __init__(self, agent_id: str, builder: Callable[[], Agent],
                 name: str | None = None, description: str | None = None) -> None:
        self.id = agent_id
        self.name = name or agent_id
        self.description = description or f"Per-request grounded agent for the {agent_id} domain."
        self._builder = builder
```
`app/agents/platform.py` — delete `class PerRequestPlatformAgent` and export a proxy via the generic:
```python
from app.agents.per_request import PerRequestAgent

platform_agent_proxy = PerRequestAgent(
    "platform", build_platform_agent,
    name="PlatformConcierge",
    description="Engineering-platform concierge over Microsoft first-party MCP tools.",
)
```
`app/main.py` — replace `PerRequestPlatformAgent()` with the new export:
```python
from app.agents.platform import build_platform_agent, platform_configured, platform_agent_proxy
...
        agent=platform_agent_proxy,   # was PerRequestPlatformAgent()
```
> Grep for every `PerRequestPlatformAgent` reference (`grep -rn PerRequestPlatformAgent apps/backend`) and update all — note there are **2 functional refs** (`main.py` import + instantiation) **and 3 stale comment/docstring mentions** (`main.py:75`, `main.py:118`, `per_request.py:10`); fix the comments too (esp. `main.py:118`'s "The PerRequestPlatformAgent proxy rebuilds…") so no dangling prose remains. The collapse is a pure refactor — the live `/platform` per-request rebuild is identical (the proxy still calls `build_platform_agent()` per `.run()`). **Self-hosted byte-identical.**

- [ ] **Step 4: Run the test, expect PASS.**

- [ ] **Step 5: Regression** — `shared_boot_smoke_test` + import `app.main` in self_hosted both still work (the platform endpoint still registers a `SupportsAgentRun`).
```bash
cd apps/backend && uv run python -m eval.shared_boot_smoke_test && DEPLOYMENT_MODE=self_hosted uv run python -c "import app.main; print('ok')"
```

- [ ] **Step 6: Commit**
```bash
cd /Users/jefferson.barnabe/projects/foundry-helpdesk
git add apps/backend/app/agents/per_request.py apps/backend/app/agents/platform.py apps/backend/app/main.py apps/backend/eval/per_request_override_test.py
git commit -m "refactor(D-packaging): collapse PerRequestPlatformAgent into PerRequestAgent (name/description override)"
```

---

### Task 9: #3199 write-approval-over-AG-UI live verification (+ conditional middleware)

**Files:** `docs/superpowers/notes/` (the verification procedure + result); conditionally `app/agents/mcp/approval_middleware.py` (only if the live check fails).

> This is a verification + a CONDITIONAL implementation. The live firing needs a running stack (infra-gated); the deliverable now is the documented procedure + the decision, and the middleware ONLY if the check shows #3199 unfixed.

- [ ] **Step 1: Determine #3199 status from the installed version**
```bash
cd apps/backend
uv run python -c "import agent_framework, importlib.metadata as m; print('agent_framework', m.version('agent-framework'))"
```
Cross-check the agent-framework changelog / issue #3199 for whether `approval_mode=always_require_approval` executes over the AG-UI adapter in this version. Record in a note (`docs/superpowers/notes/d-packaging-3199.md`).

- [ ] **Step 2: Document the live-verification procedure** — with a running shared stack + a write-tool request on `/platform` (live) and `/platform-hosted`: confirm the approval interrupt surfaces as the `request_info` CUSTOM event `TicketApproval.tsx` consumes, and that resume executes the write. Mark infra-gated (needs the running stack).

- [ ] **Step 3: Conditional middleware (ONLY if Step 1/live shows #3199 unfixed)** — implement a framework `RequestInfoEvent`-emitting middleware (ADR-009's stated fallback; NOT a hand-rolled workflow) that pauses write tools and emits the approval interrupt. If #3199 is fixed → no code; record "native, no middleware needed." Do not build the middleware speculatively.

- [ ] **Step 4: Commit** (the note, + middleware only if built)
```bash
cd /Users/jefferson.barnabe/projects/foundry-helpdesk
git add docs/superpowers/notes/d-packaging-3199.md
git commit -m "docs(D-packaging): #3199 write-approval-over-AG-UI status + live-verify procedure"
```

---

## Final verification

- [ ] **Infra-free suite green offline:**
```bash
cd apps/backend
for t in hosted_platform_smoke platform_hosted_bridge tier_domains per_request_override; do
  echo "== $t ==" && uv run python -m eval.${t}_test || exit 1
done
echo "== infra-gated (skip clean) ==" && uv run python -m eval.platform_hosted_e2e_test
```
Expected: each infra-free test `✅`; `platform_hosted_e2e` `⏭ skipped`.

- [ ] **No A/B/C/D-runtime regression:**
```bash
cd apps/backend
for t in tenant_store tenant_resolution domain_gate domains_api configured_mode shared_boot_smoke rbac_per_tool hosted_build onboarding_guard; do
  uv run python -m eval.${t}_test || exit 1
done
```
Expected: all PASS (every change mode-gated/additive; self-hosted untouched).

- [ ] **IaC compiles where the toolchain exists:** `infra/managed-app/build.sh` produces `mainTemplate.json`; `infra/lighthouse` compiles. (Else the documented offline gate per Task 4/5.)

- [ ] **Final full-branch review**, then `superpowers:finishing-a-development-branch` → PR into `develop` (after D-runtime PR #80 merges, since this is stacked on it).

---

## Notes for the executor

- **Phase 1 is gated by Task 0.** Do not write `apps/hosted-platform/main.py`'s host-server/tool lines or `stream_platform_agui`'s relay until Task 0 records the verified `InvocationsHostServer` signature, the Toolbox config surface, and the bridge client choice. Where Task 0 says "not determinable offline," fence it `TODO(infra-gated)` and reference the Toolbox by env — never hand-roll credential code (ADR-011, rule #1).
- **The envelope is AG-UI.** The bridge is a passthrough — relay the SSE bytes untouched; do not parse/re-encode (that's the whole point of using Invocations, per ADR-011).
- **Self-hosted byte-identical.** Phase 3's tier→domains keeps "all by default" for the bodyless onboard; the PerRequest collapse is a pure refactor. The live `/platform` and every self_hosted path must behave identically.
- **Infra-gated ≠ fabricated.** Marketplace publish, Lighthouse delegation, live Toolbox passthrough, and #3199 live firing are runbooks/skip-clean — never claim them as passing.
- **Stacked branch.** This sits on D-runtime; its PR targets `develop` after #80 merges (or rebase onto develop once #80 lands).
