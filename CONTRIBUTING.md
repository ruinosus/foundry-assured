# Contributing

How we work on Foundry Assured. Setup lives in [`docs/DEPLOYMENT.md`](./docs/DEPLOYMENT.md);
this is the workflow + repo-governance guide.

## Branching & flow (trunk-based)

`main` is always releasable and protected. Work happens on short-lived branches off
`main`, merged back via PR.

```
main ──●──────●─────────●───►
        \    /          /
         feat/…    fix/…   (branch → PR → squash-merge)
```

- **Branch names:** `feat/<short-desc>`, `fix/<short-desc>`, `chore/…`, `docs/…`, `ci/…`.
- **One PR = one concern.** Keep them small and reviewable.
- **Squash-merge** into `main` (linear history); the PR title becomes the commit.

## Commits & PR titles — Conventional Commits

```
<type>(<scope>): <summary>

feat(eval): add safety/jailbreak judges
fix(chat): refresh the OBO token before it expires
chore(deps): bump agent-framework to 1.9.1
```

Types: `feat`, `fix`, `chore`, `docs`, `refactor`, `test`, `ci`, `build`, `perf`.
Scopes: `backend`, `frontend`, `hosted-agent`, `infra`, `eval`, `auth`, `deps`, …

## Pull requests

1. Open against `main`, fill the PR template, link the issue (`Closes #123`).
2. **CI must be green** — the `CI passed` check (policy gate + typecheck + build + bicep).
3. At least **one approving review** (CODEOWNERS auto-requested).
4. Resolve threads, then squash-merge.

## Project rules (from [`CLAUDE.md`](./CLAUDE.md))

- **Never invent SDK signatures.** Verify against the installed package / Microsoft
  docs before fixing any `azure-ai-projects` / `agent-framework` call.
- **Agent prompts** change only in `apps/backend/agents/helpdesk/` — one
  [AgentSchema](https://github.com/microsoft/AgentSchema) `PromptAgent` per agent holding its
  variant delta, the shared persona in `personas/`, cross-cutting rules in `guardrails/`
  ([ADR-013](./docs/adr/ADR-013-declarative-agent-prompts-dna.md),
  [ADR-015](./docs/adr/ADR-015-agentschema-replaces-the-dna-sdk.md)); `app/agents/prompts.py` is the
  single consumption point and composes them at import. When a prompt contract changes, update the
  matching case in `agents/helpdesk/eval-cases/` in the same PR —
  `uv run python -m eval.prompt_contract_test` is the CI guard.
- Auth is **keyless** (`DefaultAzureCredential` / OBO) — no API keys in code.
- Every resolver answer **must cite a source** (the eval policy gate enforces it).
- Never commit secrets or `.env` values.

## Work tracking — the in-repo DNA SDLC board

Non-trivial work is tracked as versioned YAML in **`.dna/foundry-dev/`** (features/stories +
timelines), driven by the [`dna` CLI](https://github.com/ruinosus/dna). This is a **dev-time tool**,
not a dependency of anything the product runs: the backend's agent definitions moved to AgentSchema
in [ADR-015](./docs/adr/ADR-015-agentschema-replaces-the-dna-sdk.md) and `dna-sdk` is no longer
installed by any app here. Install the CLI from PyPI: `uv tool install dna-cli`.

Basics, from the repo root with `DNA_BASE_DIR=$PWD/.dna`: `dna sdlc story create s-x --feature f-y
--ac … --dod …` → `story start s-x --plan "…"` → narrate with `story comment` as you work →
`story pr s-x --base main` → `story done s-x` on merge. One-time per clone: `dna sdlc hooks install`
— commits made while a story is active get a `Work-Item: Story/<name>` trailer automatically.
Full conventions live in the [DNA repo docs](https://github.com/ruinosus/dna/tree/main/docs).

## Code style

- **Backend:** ruff (`uvx ruff check apps/backend`), thin routers → services → core.
- **Frontend:** `npm run typecheck` + `npm run lint`; feature-organized `components/<area>/`, `@/` imports.
- **Infra:** keep Bicep compiling (`bicep build infra/main.bicep`).

## CI/CD

| Workflow | Trigger | Does |
| --- | --- | --- |
| `ci.yml` | PR + push to `main` | policy gate · typecheck · build · bicep (the required check) |
| `security-gates.yml` | PR + manual | assurance security gates: access-control (`eval/access_control_test.py`) + red-team (`eval/red_team_test.py`) — a cross-group leak or over-ceiling ASR fails the build |
| `agent-evals.yml` | manual | Microsoft's official `ai-agent-evals` action on the deployed hosted agent (groundedness/relevance/coherence/intent) — advisory in the run summary, does not block |
| `eval-cloud.yml` | weekly + manual | Foundry groundedness/relevance/coherence (+ `--safety`) |
| `deploy.yml` | manual | `azd` deploy backend + frontend to Container Apps |
| `provision-kb.yml` | manual | re-ingest the knowledge base |
| `wiki-freshness.yml` | push to `main` + weekly + callable | detects wiki drift. **Not a PR check** — it is the trigger `wiki-regen.yml` consumes ([ADR-016](./docs/adr/ADR-016-openwiki-closes-the-freshness-loop.md)) |
| `wiki-regen.yml` | manual | on drift: OpenWiki regenerates → adapter → **fidelity gate** → opens a PR. Needs the OpenWiki config below |
| `release.yml` | push to `main` | release-please: version bump + changelog + tag (needs the GitHub App, below) |

### One-time GitHub setup (for the Azure workflows)

The cloud workflows authenticate to Azure with **OIDC** (no stored credentials).

1. **Create an Entra app + federated credential** for the repo:
   ```bash
   az ad app create --display-name foundry-assured-ci
   # note the appId; create a service principal and grant it Contributor on rg-<env>.
   # The DATA-plane roles are NOT granted by hand — the Bicep declares them (see step 4).
   az ad app federated-credential create --id <appId> --parameters '{
     "name": "github-main",
     "issuer": "https://token.actions.githubusercontent.com",
     "subject": "repo:ruinosus/foundry-assured:ref:refs/heads/main",
     "audiences": ["api://AzureADTokenExchange"]
   }'
   # repeat with subject "repo:ruinosus/foundry-assured:environment:production" for the deploy env
   ```
2. **Repository → Settings → Secrets and variables → Actions:**
   - **Variables:** `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`,
     `AZURE_ENV_NAME`, `AZURE_LOCATION`, `FOUNDRY_PROJECT_ENDPOINT`, `FOUNDRY_MODEL`,
     `AZURE_SEARCH_ENDPOINT`, `AZURE_SEARCH_KNOWLEDGE_BASE`, `AZURE_STORAGE_*`,
     `NEXT_PUBLIC_ENTRA_*`, `ENTRA_TENANT_ID`, `ENTRA_API_CLIENT_ID`.
     - For **`security-gates.yml`** (assurance security gates): `COCKPIT_TEST_USER_A`,
       `COCKPIT_TEST_USER_B` (the two test identities the access-control / red-team gates
       run as). Entitlement is derived from the live search ACL, so the `COCKPIT_ACL_*_GROUP`
       trio (`COCKPIT_ACL_PUBLIC_GROUP` / `_INTERNAL_GROUP` / `_CONFIDENTIAL_GROUP`) is only
       needed if you ingest with the demo group map rather than your own `COCKPIT_ACL_GROUP_MAP`.
     - For **`release.yml`** (release-please GitHub App): `RELEASE_APP_ID`.
   - **Secrets:** `ENTRA_API_CLIENT_SECRET`; `COCKPIT_TEST_PASSWORD` (test-identity password
     for the security gates); `RELEASE_APP_PRIVATE_KEY` (the release GitHub App key).
   The variables above are **derived from the azd environment** — do not type them by hand.
   `./scripts/sync-gh-variables.sh` reports drift and `--apply` writes them; they silently
   drifted through a resource rename once and every scheduled cloud run failed for eight weeks.
3. **Environments → `production`:** add required reviewers (gates `deploy.yml` / `provision-kb.yml`).
4. **Grant the CI identity its data-plane roles — through the Bicep, never by hand:**
   ```bash
   azd env set AZURE_CI_PRINCIPAL_ID "$(az ad sp show --id <appId> --query id -o tsv)"
   azd provision      # creates Azure AI User + Search Service/Index Contributor + Storage Blob Data Contributor
   ```
   `Contributor` is control-plane only; without this the cloud workflows reach Azure and then 403
   on the Foundry and Search data planes. Assigning the roles with `az role assignment create`
   instead would break the next provision — the template names assignments
   `guid(scope, principal, role)`, and the CLI mints a random name for the same triple.
5. **For `wiki-regen.yml` (optional — only if you run the wiki loop):**
   - **Variables:** `OPENWIKI_BASE_URL` (an Azure OpenAI `/openai/v1` endpoint — OpenWiki has no
     `azure` provider, but its `openai-compatible` one takes that surface directly),
     `OPENWIKI_MODEL` (a deployment name; a small model stalls on this job).
   - **Secret:** `OPENWIKI_API_KEY` — sent as a bearer token, which the Azure `v1` surface accepts.

   Leave them unset and the workflow simply cannot run; nothing else is affected.

> **Separate from CI:** the `foundry-assured-ci` app above is the *deploy* identity. The
> **runtime** app also needs **app-only Microsoft Graph permissions** for the RBAC / admin
> portal (App Roles + `/admin/users`) — set up out-of-band via `scripts/setup-app-roles.sh`,
> not here. See [`docs/RBAC-AND-USER-MANAGEMENT-PLAN.md`](./docs/RBAC-AND-USER-MANAGEMENT-PLAN.md).

### Branch protection (Settings → Branches → `main`)

- Require a pull request before merging · **1 approval** · dismiss stale approvals.
- Require status checks to pass → **`CI passed`**.
- Require conversation resolution · require linear history · include administrators.
