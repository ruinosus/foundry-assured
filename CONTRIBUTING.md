# Contributing

How we work on Foundry Helpdesk. Setup lives in [`docs/DEPLOYMENT.md`](./docs/DEPLOYMENT.md);
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
- **Agent prompts** change only in `apps/backend/app/agents/prompts.py` (single source).
- Auth is **keyless** (`DefaultAzureCredential` / OBO) — no API keys in code.
- Every resolver answer **must cite a source** (the eval policy gate enforces it).
- Never commit secrets or `.env` values.

## Code style

- **Backend:** ruff (`uvx ruff check apps/backend`), thin routers → services → core.
- **Frontend:** `npm run typecheck` + `npm run lint`; feature-organized `components/<area>/`, `@/` imports.
- **Infra:** keep Bicep compiling (`bicep build infra/main.bicep`).

## CI/CD

| Workflow | Trigger | Does |
| --- | --- | --- |
| `ci.yml` | PR + push to `main` | policy gate · typecheck · build · bicep (the required check) |
| `eval-cloud.yml` | weekly + manual | Foundry groundedness/relevance/coherence (+ `--safety`) |
| `deploy.yml` | manual | `azd` deploy backend + frontend to Container Apps |
| `provision-kb.yml` | manual | re-ingest the knowledge base |

### One-time GitHub setup (for the Azure workflows)

The cloud workflows authenticate to Azure with **OIDC** (no stored credentials).

1. **Create an Entra app + federated credential** for the repo:
   ```bash
   az ad app create --display-name foundry-helpdesk-ci
   # note the appId; create a service principal and grant it Contributor + the
   # Foundry/Search data-plane roles on rg-<env>
   az ad app federated-credential create --id <appId> --parameters '{
     "name": "github-main",
     "issuer": "https://token.actions.githubusercontent.com",
     "subject": "repo:OWNER/REPO:ref:refs/heads/main",
     "audiences": ["api://AzureADTokenExchange"]
   }'
   # repeat with subject "repo:OWNER/REPO:environment:production" for the deploy env
   ```
2. **Repository → Settings → Secrets and variables → Actions:**
   - **Variables:** `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`,
     `AZURE_ENV_NAME`, `AZURE_LOCATION`, `FOUNDRY_PROJECT_ENDPOINT`, `FOUNDRY_MODEL`,
     `AZURE_SEARCH_ENDPOINT`, `AZURE_SEARCH_KNOWLEDGE_BASE`, `AZURE_STORAGE_*`,
     `NEXT_PUBLIC_ENTRA_*`, `ENTRA_TENANT_ID`, `ENTRA_API_CLIENT_ID`.
   - **Secrets:** `ENTRA_API_CLIENT_SECRET`.
3. **Environments → `production`:** add required reviewers (gates `deploy.yml` / `provision-kb.yml`).

### Branch protection (Settings → Branches → `main`)

- Require a pull request before merging · **1 approval** · dismiss stale approvals.
- Require status checks to pass → **`CI passed`**.
- Require conversation resolution · require linear history · include administrators.
