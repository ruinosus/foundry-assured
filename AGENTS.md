# AGENTS.md — working in Foundry Assured

**Foundry Assured** is a Microsoft Foundry showcase: an internal engineering-support
**concierge** that triages a developer's question, retrieves from a grounded knowledge
base, resolves with a cited answer, and escalates with human approval when an action is
needed — every answer **evaluated** and **traceable**. On top of the showcase it ships a
reusable **assurance mechanism** (measured, CI-gated guarantees) and a **hybrid
multi-tenant SaaS** seam (one codebase, three deployment modes). It is a **product** —
Azure + FastAPI + Next.js — not a library.

This file is the canonical, agent-agnostic onboarding surface (an
[`agents.md/v1`](https://agents.md) instance read by 28+ agent tools, and parsed
round-trip by the DNA SDK). It is the **quick orientation**; the deep, opinionated
working rules — phases, SDK-signature discipline, the non-negotiables — live in
[`CLAUDE.md`](./CLAUDE.md) and are not duplicated here. Read this first, then CLAUDE.md
for depth. Full navigable docs: the [documentation site](https://ruinosus.github.io/foundry-assured/)
(Diátaxis — tutorials / how-to / reference / explanation), sourced from [`docs/`](./docs/).

## Layout

```
apps/backend/       Python 3.12 · FastAPI · agent-framework · uv
  app/{core,api,services,agents,workflow,tools,knowledge}   thin routers → services → core
  app/.dna/         DECLARATIVE agent prompts (ADR-013) — helpdesk/cockpit/selfwiki/platform scopes
  cli/  eval/        data-plane provisioning scripts · offline eval harness (Phase 5)
apps/frontend/      Next.js 15 (App Router) · CopilotKit v2 · MSAL — the "Assurance Console"
  lib/domains.ts    the domain registry: add a domain = 1 entry here + a backend agent
apps/hosted-*/      hosted-agent / hosted-platform / hosted-cockpit / hosted-selfwiki (Phase 6 deploys)
infra/              Bicep (azd): Foundry + AI Search + Storage + ACR + Container Apps + managed-app/lighthouse
scripts/            azd hooks, bootstrap, push-prompts.sh, git-hooks/ (versioned)
docs/               Diátaxis-typed docs, ADRs (docs/adr/), generated wiki (docs/wiki/), superpowers/ plans+specs
.dna/foundry-dev/   THIS repo's dev-time SDLC board (Stories/Features/Plans/TestGuides) — NOT the runtime prompts
azure.yaml          azd config — services point at apps/{backend,frontend,hosted-agent}
```

> **Two `.dna` roles, don't confuse them.** `.dna/foundry-dev/` (repo root) is the
> **dev-time SDLC board** (this document's `dna sdlc` protocol). `apps/backend/app/.dna/`
> is the **runtime prompt scope** — the declarative agent instructions the product composes
> at boot (ADR-013). Editing a prompt = edit a YAML there, **restart, not rebuild** (ADR-014).

## Build, test & run

```bash
# Backend (from apps/backend/)
uv sync                                         # deps (uv, frozen in CI)
uv run uvicorn app.main:app --port 8000 --reload
uv run python -m eval.run_eval --self-test      # the CI policy gate (planted-violation self-test)

# Frontend (from apps/frontend/)
npm ci && npm run typecheck && npm run build    # what CI gates
npm run dev                                     # http://localhost:3000
npm run demo                                    # NO Azure: replays recorded AG-UI fixtures

# Infra
bicep build infra/main.bicep --stdout > /dev/null   # compile-check (CI)

# Whole stack, one command
./scripts/up-all.sh
```

**CI gate = the `CI passed` check** (`.github/workflows/ci.yml`): backend (ruff advisory +
policy gate + artifact/ACL/eval tests + the `dna eval` prompt-invariant suite), frontend
(typecheck + build), infra (bicep). Keep it green; it is the one required status check. The
`docs` workflow (`.github/workflows/docs.yml`) is **separate** and never feeds `CI passed`.
(The `deep-wiki tracks the code` check is known-broken and ignored.)

## Deploy & gitflow

- **Gitflow.** `develop` is the integration line (base your PRs here); it is promoted to
  `main` in batches. `main` being behind `develop` is normal. release-please cuts versioned
  releases off `main` → gated production deploy (see `docs/RELEASE-AUTOMATION.md`).
- **Provision + deploy** with `azd` (Bicep is control-plane only; the KB + memory are
  data-plane objects created by scripts). Runbook: `docs/DEPLOYMENT.md`. Both apps ship as
  containers to **Azure Container Apps**.
- **Prompts without redeploy.** Edit the YAML under `apps/backend/app/.dna/<domain>/`,
  restart the process (local: bind-mount; prod ACA: Azure Files at `/mnt/dna` via
  `DNA_BASE_DIR`). `scripts/push-prompts.sh` pushes the scope. **No image rebuild** (ADR-014).

## Non-negotiables (the short list — full rationale in CLAUDE.md)

- **Never invent SDK signatures** (esp. `azure-ai-projects` `.beta`). Verify against Microsoft
  Learn / foundry-samples or leave an explicit `# TODO: verificar assinatura`.
- **Auth is always `DefaultAzureCredential`** — no hardcoded keys.
- **Every resolver answer carries ≥1 source citation** (eval policy — ASSERT fails otherwise).
- **`create_ticket` only after explicit human approval** (HITL), gated by the Entra **Approver**/**Admin** role.
- **Access control is DATA, never classification logic in code** — access follows the source; no access → fail-closed.
- **Agent prompts are declarative** (`apps/backend/app/.dna/`, ADR-013) — don't hardcode a prompt/persona in Python.

## SDLC protocol — work is tracked in-repo via `dna sdlc`

This repo tracks its own lifecycle as DNA documents in `.dna/foundry-dev` (board scope
`foundry-dev`). The flow is **story-first**: file the Story before the work, narrate while
building, verify before closing. The `dna` CLI is the published `dna-cli` package.

```bash
dna sdlc brief                          # session start — what's in flight
dna sdlc hooks install                  # one-time per clone — commit trailers
dna sdlc story create s-my-work --feature f-x --desc "..." \
  --ac "Given/When/Then ..." --dod "code+tests+docs ..."   # AC + DoD required
dna sdlc story start s-my-work --plan-file plan.md          # plan gate
dna sdlc story comment s-my-work --body "decided X because Y"  # narrate as you go
dna sdlc test-guide create tg-my-work --verifies Story/s-my-work --step "run :: expect"
dna sdlc test-run record tg-my-work --outcome pass          # test gate for done
dna sdlc story pr s-my-work --base develop  # gh pr create, pre-filled FROM the story
dna sdlc story done s-my-work           # only after the PR merges
```

While a story is active, every commit is stamped with `Work-Item:` + `dna-sdlc[bot]`
trailers by the versioned hook (`scripts/git-hooks/`) — the provenance seal linking git
history to the work item (`dna sdlc story commits s-x`).

## Conventions

- **Story-first.** Non-trivial work starts with `dna sdlc story create` (AC + DoD mandatory)
  and `story start` (the plan gate — substantial work gets a real `--plan-file`, not a one-liner).
- **Narrate as you go.** Status changes record *that* something happened, not *what*. Post
  `dna sdlc story comment` for each meaningful step/decision — the timeline is what future sessions read.
- **Gapless definition of done.** Never mark `done` with a gap: finish to market standard, or
  keep `in-progress` / decompose. `story done` requires a passing TestRun.
- **Review = open PR; done = merged.** A story in `review` with no PR is stale. Once a PR is
  approved, stop pushing to its branch — further work goes to a new branch off the merged base.
- **Surface IDs** in backticks (`s-foo`, `f-bar`) so they paste into `dna sdlc story show`.

## Do not

- **Never hand-edit `.dna/**.yaml` for status changes** — the CLI is the canonical write path
  (validation, timeline and journey events fire there).
- **Never do non-trivial work without an active story** — unstamped commits are invisible to
  `story commits` / `story show`; absence is signal.
- **Never break `CI passed`** — the docs site is a separate workflow; product gates stay green.

## Learn more

- **Skill:** the `dna-sdlc-cli` skill (agentskills.io `SKILL.md`) is projected by `dna init`
  into `.claude/skills/`, `.github/skills/`, `.cursor/skills/` — the full CLI workflow.
- **Working rules (depth):** [`CLAUDE.md`](./CLAUDE.md) — phases, SDK discipline, architecture.
- **Docs site:** <https://ruinosus.github.io/foundry-assured/> · sources in [`docs/`](./docs/)
  ([`docs/DOCS-STANDARD.md`](./docs/DOCS-STANDARD.md) for the Diátaxis conventions).
