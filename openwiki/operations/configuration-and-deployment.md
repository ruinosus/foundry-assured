---
type: operational concept
title: Configuration, local/dev modes, and deployment paths
description: Repository-specific map of the configuration seams across backend, frontend, and MCP, plus the local, demo, CI, and Azure deployment entrypoints that shape how engineers and automation run the system.
tags: [operations, configuration, deployment, azure, local-development, ci-cd]
verified:
  - by: openwiki/0.4.3
    at: 2026-09-02T18:24:34.393Z
sources:
  - id: openwiki-source-164e2da859b5277df81c7d94
    resource: repo://.github/workflows/ci.yml
  - id: openwiki-source-6766b7a0c14857435d2077c9
    resource: repo://.github/workflows/deploy.yml
  - id: openwiki-source-a930fae736bfac96e4909803
    resource: repo://apps/backend/.env.example
  - id: openwiki-source-f4519c31e331789986101d29
    resource: repo://apps/backend/app/shared/settings.py
  - id: openwiki-source-205f068b491557e4403b3567
    resource: repo://apps/backend/compose.yaml
  - id: openwiki-source-0d56c09af4284d4ebd53deef
    resource: repo://apps/frontend/.env.example
  - id: openwiki-source-8da440bd83bf60dffa8f176d
    resource: repo://apps/frontend/lib/demo.ts
  - id: openwiki-source-737747352fba963c524e7bf7
    resource: repo://apps/frontend/lib/frontend-mode.ts
  - id: openwiki-source-10b4a98f536331e1a0a23c59
    resource: repo://apps/frontend/package.json
  - id: openwiki-source-5545ab5415f982e19c1a0070
    resource: repo://azure.yaml
  - id: openwiki-source-1f2994ce2c818471371d726c
    resource: repo://docs/DEPLOYMENT.md
  - id: openwiki-source-23775c3de52f3ab95a13cb8b
    resource: repo://README.md
  - id: openwiki-source-398b4479abcecdb45ae1fc66
    resource: repo://scripts/demo-record.sh
  - id: openwiki-source-54210f9f1b0d6086208ecde2
    resource: repo://scripts/demo.sh
  - id: openwiki-source-2aedf19a0cc5373e0bfe86a5
    resource: repo://scripts/hook-postdeploy.sh
  - id: openwiki-source-7a1a958aac9f31ed9cbf91e1
    resource: repo://scripts/hook-postprovision.sh
  - id: openwiki-source-48fb3749b938524a338de38b
    resource: repo://scripts/up-all.sh
generated: { by: "openwiki/0.4.3", at: "2026-09-02T18:24:34.393Z" }
---

# Configuration, local/dev modes, and deployment paths

This repository has three distinct operational surfaces that engineers configure and run differently:

- the **backend** (`apps/backend`), which owns platform-global settings like auth, deployment mode, CORS, and MCP enablement while tenant/domain data-plane pointers live elsewhere; [`apps/backend/app/shared/settings.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/app/shared/settings.py#L1-L128)
- the **frontend** (`apps/frontend`), which mostly derives its runtime URLs from `BACKEND_URL` and then layers UI/data/demo switches on top; [`apps/frontend/.env.example`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/frontend/.env.example#L1-L28)
- the **standalone MCP server** (`apps/mcp`), which is not served by the backend anymore and is deployed as its own `azd` service; [`azure.yaml`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/azure.yaml#L6-L26)

The practical seam is that configuration is not “one env file for the whole product”. The backend `.env` carries Azure/Foundry/Search/Storage/auth and MCP server coordination values, the frontend `.env.local` carries browser-visible Entra ids and endpoint selection, and Azure deployment pushes a subset of those values into the `azd` environment before image build so the web image is built with the right public config. [`apps/backend/.env.example`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/.env.example#L13-L128) [`scripts/hook-postprovision.sh`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/scripts/hook-postprovision.sh#L1-L17) [`azure.yaml`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/azure.yaml#L75-L94)

## Configuration seams by surface

## Backend: platform-global settings, deployment mode, and Azure pointers

The backend example env is organized by operational responsibility rather than by file owner:

- **Foundry/model settings**: `FOUNDRY_PROJECT_ENDPOINT`, `FOUNDRY_MODEL`, `FOUNDRY_EMBEDDING_MODEL`, `AZURE_AI_OPENAI_ENDPOINT`.
- **Knowledge base/corpus settings**: `AZURE_SEARCH_ENDPOINT`, `AZURE_SEARCH_KNOWLEDGE_BASE`, `AZURE_STORAGE_ACCOUNT`, `AZURE_STORAGE_RESOURCE_ID`, `AZURE_STORAGE_CONTAINER`.
- **Auth/deployment settings**: `ENTRA_*`, `DEPLOYMENT_MODE`, `FRONTEND_ORIGIN`, `ONBOARDING_ALLOWED_TIDS`.
- **ACL settings**: `APP_USERS_GROUP_ID`, `ACL_*`.
- **Per-domain KB names** for `techdocs` and `selfwiki`.
- **Platform/MCP settings** like `MCP_ENABLED`, `PUBLICATION_TOOLBOX_ENDPOINT`, `MCP_PUBLIC_BASE_URL`, `MCP_REQUEST_STATE_KEY`, `MCP_REDIS_URL`, `FASTMCP_TASKS_ENCRYPTION_KEY`.
- **Shared-mode tenant store settings** and optional observability/tuning knobs. [`apps/backend/.env.example`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/.env.example#L13-L128)

What matters operationally is that `app/shared/settings.py` intentionally keeps only **platform-global** settings. It defaults `deployment_mode` to `self_hosted`, enables auth only when the backend API registration is configured, keeps `mcp_enabled` as a deployment switch, and sets the MCP public base URL default to `http://localhost:8001` because the standalone MCP app listens there in dev. [`apps/backend/app/shared/settings.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/app/shared/settings.py#L16-L28) [`apps/backend/app/shared/settings.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/app/shared/settings.py#L37-L58) [`apps/backend/app/shared/settings.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/app/shared/settings.py#L73-L82) [`apps/backend/app/shared/settings.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/app/shared/settings.py#L114-L125)

Two defaults define the local behavior envelope:

- if `ENTRA_TENANT_ID` and `ENTRA_API_CLIENT_ID` are absent, `auth_enabled` is false and the app falls back to the no-sign-in path for local development; [`apps/backend/app/shared/settings.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/app/shared/settings.py#L114-L121)
- if `MCP_REQUEST_STATE_KEY` is blank, the MCP write approval flow is intentionally unavailable rather than partially configured; if present but too short, the server is expected to fail rather than degrade silently. The `.env.example` documents the same invariant. [`apps/backend/app/shared/settings.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/app/shared/settings.py#L84-L98) [`apps/backend/.env.example`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/.env.example#L82-L108)

`DEPLOYMENT_MODE` is also a real operational seam, not a label. The backend env declares `self_hosted | dedicated | shared`, and the settings layer defaults to `self_hosted`; separate tests in the repo exercise `shared` boot paths and enforce that shared mode needs tenant-store wiring. [`apps/backend/.env.example`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/.env.example#L29-L38) [`apps/backend/app/shared/settings.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/app/shared/settings.py#L21-L28)

## Frontend: backend-derived routing plus UI/data/demo switches

The frontend env is deliberately thinner. `BACKEND_URL` is the root seam, and domain-specific AG-UI endpoints derive from it unless explicitly overridden. On top of that, the frontend exposes:

- `NEXT_PUBLIC_FRONTEND_MODE=legacy | assured`
- `NEXT_PUBLIC_DATA_MODE=connected | local`
- the browser-side `NEXT_PUBLIC_ENTRA_*` ids
- optional `NEXT_PUBLIC_DEMO_MODE` for fixture replay. [`apps/frontend/.env.example`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/frontend/.env.example#L6-L28)

The code normalizes those switches with safe fallbacks: frontend mode defaults to `legacy`, data mode defaults to `connected`, and `isLocalDataMode` is derived from that validated value. [`apps/frontend/lib/frontend-mode.ts`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/frontend/lib/frontend-mode.ts#L1-L23)

The sign-in seam matches the backend one: leaving `NEXT_PUBLIC_ENTRA_*` blank is the supported no-auth local mode, and deployment has to inject those ids into the build-time environment before the web image is built. [`apps/frontend/.env.example`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/frontend/.env.example#L21-L28) [`scripts/hook-postprovision.sh`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/scripts/hook-postprovision.sh#L2-L17)

## MCP: separate deployment unit, shared settings source

The repository’s MCP server is a separate `azd` service named `mcp`, hosted as its own Container App with its own Docker build context. That separation exists because `apps/mcp` depends on `apps/backend` by path, so the Docker build needs the repository root in scope. [`azure.yaml`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/azure.yaml#L14-L26)

Even though it is separately deployed, it still reads the same shared settings package for values like `mcp_public_base_url` and `mcp_request_state_key`; `app/shared/settings.py` documents that this is intentional so the repo does not grow a second independent settings class for the same cross-surface values. [`apps/backend/app/shared/settings.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/app/shared/settings.py#L76-L82) [`apps/backend/app/shared/settings.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/app/shared/settings.py#L84-L112)

Operationally, that means the MCP server has its own deploy lifecycle, but not an entirely separate configuration vocabulary.

## Local and demo run modes

## Standard local development: provisioned Azure, locally run app processes

The primary local/dev path in both `README.md` and `docs/DEPLOYMENT.md` is:

1. authenticate with `azd auth login` and `az login`
2. provision with `azd up`
3. optionally set up Entra registrations with `./scripts/setup-entra.sh`
4. bootstrap data-plane resources with `./scripts/bootstrap.sh`
5. run backend and frontend locally with `uvicorn` and `npm run dev`. [`README.md`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/README.md#L117-L130) [`docs/DEPLOYMENT.md`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/docs/DEPLOYMENT.md#L18-L43)

The important lifecycle ordering is that `azd up` handles control-plane resources, while knowledge-base ingest and memory provisioning are explicit **data-plane** stages rather than hidden hooks. `docs/DEPLOYMENT.md` calls out that ingest is per-domain and manual/explicit; `scripts/up-all.sh` keeps bootstrap visible for the same reason. [`docs/DEPLOYMENT.md`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/docs/DEPLOYMENT.md#L175-L210) [`scripts/up-all.sh`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/scripts/up-all.sh#L105-L110)

For auth, the repo explicitly supports a no-sign-in local fallback: skip `setup-entra.sh`, leave the `ENTRA_*` values blank, and the backend uses the single-identity `DefaultAzureCredential` path instead of OBO. The frontend mirrors that by allowing blank `NEXT_PUBLIC_ENTRA_*` values. [`docs/DEPLOYMENT.md`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/docs/DEPLOYMENT.md#L30-L43) [`apps/backend/.env.example`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/.env.example#L29-L38) [`apps/frontend/.env.example`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/frontend/.env.example#L21-L25)

## One-command local orchestration: `scripts/up-all.sh`

`scripts/up-all.sh` is the repository’s highest-level local provisioning entrypoint. It performs preflight checks, optionally creates Entra app registrations and app roles before provisioning, runs `azd up`, then runs bootstrap. The script is intentionally idempotent and documents why the ordering matters:

- auth must happen **before** `azd up` if the deployed web image should bake in the `NEXT_PUBLIC_*` values
- `azd` hooks automate env push, hosted-agent RBAC, and SPA redirect URI reconciliation
- bootstrap stays explicit because ingest is slow and data-plane fragile. [`scripts/up-all.sh`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/scripts/up-all.sh#L2-L16) [`scripts/up-all.sh`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/scripts/up-all.sh#L68-L110)

This script is therefore the best summary of the intended lifecycle, while `docs/DEPLOYMENT.md` is the longer reference.

## Backend container loop: restart, not rebuild, for prompt edits

`apps/backend/compose.yaml` is not a general multi-service dev stack; it is a narrow local backend loop for editing agent definitions without rebuilding the image. The compose file bind-mounts `./agents` read-only over the image’s baked-in copy and documents that refresh semantics are **restart-grade**, not hot-reload-grade: edit prompt YAML, then `docker compose restart backend`, not rebuild. [`apps/backend/compose.yaml`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/compose.yaml#L1-L25)

That matters because the app composes prompt constants at import time and builds agents at boot, so restart is the honest operational unit.

## Demo mode: frontend-only replay with recorded AG-UI fixtures

Demo mode is a separate path for showing the product without Azure or a Python backend. The frontend package exposes `npm run demo`, which shells out to `scripts/demo.sh`; the script requires a recorded fixture under `apps/frontend/demo/fixtures`, starts CopilotKit `aimock` on a local port, sets `AGUI_URL`, `HOSTED_AGUI_URL`, and `NEXT_PUBLIC_DEMO_MODE=1`, then runs the real Next.js frontend. [`apps/frontend/package.json`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/frontend/package.json#L5-L13) [`scripts/demo.sh`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/scripts/demo.sh#L1-L47)

The frontend code treats demo mode as `NEXT_PUBLIC_DEMO_MODE === "1"`. [`apps/frontend/lib/demo.ts`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/frontend/lib/demo.ts#L1-L5)

Fixture production is its own lifecycle: `scripts/demo-record.sh` proxies the real backend through `aimock`, records AG-UI traffic into `apps/frontend/demo/fixtures`, and is meant to be run against a real backend in no-auth mode. [`apps/frontend/package.json`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/frontend/package.json#L11-L12) [`scripts/demo-record.sh`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/scripts/demo-record.sh#L1-L27)

So the repo has three materially different “local” experiences:

- local app processes against provisioned Azure
- a narrow backend container edit/restart loop
- pure frontend fixture replay with no backend at all.

## Azure deployment and CI entrypoints

## `azd` service graph and hooks

`azure.yaml` is the authoritative deployment graph for engineers and CI. It declares:

- `backend`, `mcp`, and `web` as Container App services
- four hosted-agent services on `azure.ai.agent`
- a `postprovision` hook that runs `scripts/hook-postprovision.sh`
- a `postdeploy` hook that runs `scripts/hook-postdeploy.sh`. [`azure.yaml`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/azure.yaml#L3-L94)

Those hooks capture two configuration/deployment invariants:

- **before deploy/build**: copy local auth/public env into the `azd` environment so the web image can be built with the correct `NEXT_PUBLIC_*` values; [`scripts/hook-postprovision.sh`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/scripts/hook-postprovision.sh#L2-L17)
- **after deploy**: reconcile runtime RBAC for hosted agents, whose managed identities only exist after deployment, and patch the SPA redirect URI with the deployed web URL. [`scripts/hook-postdeploy.sh`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/scripts/hook-postdeploy.sh#L2-L15) [`scripts/hook-postdeploy.sh`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/scripts/hook-postdeploy.sh#L41-L59) [`scripts/hook-postdeploy.sh`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/scripts/hook-postdeploy.sh#L61-L86)

This is why a plain `azd up` in this repo does more than provision Bicep resources: the operational lifecycle includes postprovision env synchronization and postdeploy identity reconciliation.

## GitHub Actions CI: verification-first, no deployment side effects

`.github/workflows/ci.yml` is a large verification pipeline triggered on PRs and pushes to `main`. At the operational level it establishes that CI is primarily a **boundary gate** runner, not a deployer. The backend job installs dependencies with `uv sync --frozen`, runs lint, then a long list of offline and infra-gated tests covering policy gates, access control, wiki fidelity, prompt contracts, architecture boundaries, MCP behaviors, OKF/profile publication, and deployment config verification. [`.github/workflows/ci.yml`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/.github/workflows/ci.yml#L1-L45) [`.github/workflows/ci.yml`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/.github/workflows/ci.yml#L80-L140) [`.github/workflows/ci.yml`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/.github/workflows/ci.yml#L163-L249)

For this page, the key fact is that CI codifies many operational invariants that deployment later relies on: route surfaces, import/module boundaries, MCP egress and approval semantics, blob immutability satisfiability, and even deployment-config sanity checks.

## GitHub Actions deploy: release/manual `azd` deploy with environment gate

`.github/workflows/deploy.yml` is the production deployment entrypoint. It runs on published releases or manual dispatch, but always targets the `production` GitHub Environment so a reviewer must approve it before the job proceeds. [`.github/workflows/deploy.yml`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/.github/workflows/deploy.yml#L1-L18) [`.github/workflows/deploy.yml`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/.github/workflows/deploy.yml#L34-L45)

The job then:

- installs `azd` and the `azure.ai.agents` extension so `azd` can parse the hosted-agent services in `azure.yaml`
- logs into both `azd` and `az` using OIDC
- resolves the CI service principal object id
- writes the required `azd env` values, including Entra ids/secrets, `APP_USERS_GROUP_ID`, `AZURE_SEARCH_LOCATION`, and optional `MCP_REQUEST_STATE_KEY`
- runs `azd provision --no-prompt`
- verifies that CI actually received the required data-plane roles
- deploys the selected services, defaulting to `backend web mcp`
- runs a post-deploy config sanity gate against both the backend and MCP Container Apps. [`.github/workflows/deploy.yml`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/.github/workflows/deploy.yml#L46-L115) [`.github/workflows/deploy.yml`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/.github/workflows/deploy.yml#L116-L161)

Two repository-specific deployment seams stand out here:

- `mcp` is part of both the selectable services and the default service list, so production deployment treats it as a first-class surface rather than an optional sidecar; [`.github/workflows/deploy.yml`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/.github/workflows/deploy.yml#L13-L28) [`.github/workflows/deploy.yml`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/.github/workflows/deploy.yml#L130-L134)
- the workflow treats missing or contradictory environment propagation as a deploy failure, not just a runtime concern, by checking the container apps’ effective config after deployment. [`.github/workflows/deploy.yml`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/.github/workflows/deploy.yml#L135-L161)

## Operational invariants and failure-prone seams

A few seams recur across the docs, scripts, and workflows:

- **Build-time frontend config must be in the `azd` env before deploy** or the web image bakes the wrong `NEXT_PUBLIC_*` values. [`azure.yaml`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/azure.yaml#L75-L85) [`scripts/hook-postprovision.sh`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/scripts/hook-postprovision.sh#L2-L17) [`scripts/up-all.sh`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/scripts/up-all.sh#L68-L72)
- **Hosted-agent runtime RBAC cannot be fully expressed in predeploy Bicep**, because the instance identities are minted at deploy time; the postdeploy hook reconciles them after every deploy. [`scripts/hook-postdeploy.sh`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/scripts/hook-postdeploy.sh#L2-L7) [`scripts/hook-postdeploy.sh`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/scripts/hook-postdeploy.sh#L41-L59)
- **Data-plane setup is intentionally explicit**: `azd up` is not enough for a working knowledge-backed system until bootstrap/ingest has run. [`docs/DEPLOYMENT.md`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/docs/DEPLOYMENT.md#L175-L210) [`scripts/up-all.sh`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/scripts/up-all.sh#L105-L110)
- **No-auth local mode is supported on purpose**, but it is a different runtime envelope from OBO-backed auth. That is why both backend and frontend env examples explicitly allow blank Entra ids. [`apps/backend/.env.example`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/.env.example#L29-L38) [`apps/frontend/.env.example`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/frontend/.env.example#L21-L25)
- **MCP write/task features have stronger prerequisites than MCP read/discovery**: request-state signing requires `MCP_REQUEST_STATE_KEY`, and durable/background task behavior additionally requires Redis plus `FASTMCP_TASKS_ENCRYPTION_KEY`. [`apps/backend/.env.example`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/.env.example#L82-L108)
- **Demo mode is not “local mode with fake credentials”**; it is a different control path that replaces the backend with recorded AG-UI fixtures. [`README.md`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/README.md#L132-L150) [`scripts/demo.sh`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/scripts/demo.sh#L1-L47)

In short, engineers should think in ordered stages rather than in a single “deploy” verb:

1. choose the runtime envelope: no-auth local, provisioned local, demo replay, or cloud deploy
2. set the surface-specific config: backend, frontend, and optionally MCP/task secrets
3. provision control-plane resources with `azd`
4. propagate build-time/public env before web build
5. bootstrap data-plane resources explicitly
6. reconcile postdeploy identity/runtime seams
7. let CI/deploy gates verify the resulting configuration is coherent.
