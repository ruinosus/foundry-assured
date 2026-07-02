# docs/wiki — the project's own deep-wiki (generated)

This is a **machine-generated deep-wiki of THIS repository** — the `selfwiki` domain (the
"deep-wiki daqui"). It's the assurance mechanism turned on its own source:
[`wiki_builder.py`](../../apps/backend/app/knowledge/wiki_builder.py) read the real code of
each area of the monorepo and wrote a faithful, cited wiki bundle, gated on **build
fidelity** (≥ 80% of file citations must resolve to a real source file — see
[`assurance.yaml`](../../apps/backend/eval/assurance.yaml)).

> **Generated, not curated.** Unlike the rest of `docs/` (hand-written, follows
> [`DOCS-STANDARD.md`](../DOCS-STANDARD.md) — front-matter + Diátaxis types), the bundles
> here are machine-generated in the ingest bundle format and are **exempt from the
> front-matter rule** (the standard says so). Don't hand-edit them — regenerate.

Unlike the **Cockpit** corpus (Avanade-internal docs, read from an external path and never
committed), this corpus is generated from *this public repo*, so it's safe to version here.
It's also the input the selfwiki ingest ships to the cloud knowledge base.

## What's here

One bundle per monorepo area, in the format the ingest consumes
(`manifest.json` + `pages/page-N.md` + `llms.txt`). **Current bundles are `v0.3.0`** — regenerated
from the code at commit `3333d60` to reflect the **grounded-archetype unification** (the single
`retrieve()` seam — native agentic retrieve + the `x-ms-query-source-authorization` ACL header over a
`searchIndex` KB; the `DomainSpec` registry + `mount_domains` dispatch-by-kind replacing the
main.py/chat.py split; **grounded hosted twins dropped** so grounded runs live-OBO) on top of the
multi-tenant SaaS evolution (A→B→C→D) already captured before. `v0.3.0` was produced via the **local
Microsoft Agent-Skills path** (`wiki-architect` + `wiki-page-writer`, run by the coding agent — **no
Foundry infra**), so the manifests read `model: local-agent` (the `wiki_builder.py` Foundry pipeline
remains the other path). The superseded `v0.2.0` bundles were dropped.

| Bundle (`v0.3.0`) | Source area | Pages | Fidelity (cited paths → real file) |
| --- | --- | --- | --- |
| `foundry-helpdesk-backend/`  | `apps/backend`  | 8 | 100% (249/249) |
| `foundry-helpdesk-frontend/` | `apps/frontend` | 8 | 100% (170/170) |
| `foundry-helpdesk-infra/`    | `infra` (+ `azure.yaml`, `apps/hosted-*`, `scripts/`) | 9 | 100% (317/317) |
| `foundry-helpdesk-docs/`     | `docs`          | 8 | 100% (274/274, whole-monorepo denominator)¹ |

### What this dogfood surfaced (v0.3.0)

The mechanism found faults in itself again — each is grounded and flagged on the relevant page:

- **Orphaned hosted agents:** `azure.yaml` still declares `selfwiki-expert` **and** `cockpit-expert`
  (`azure.ai.agent`) — azd builds/deploys/RBAC-grants them (`scripts/hook-postdeploy.sh`) — but the
  grounded twins were retired, so **nothing invokes them** (no `/selfwiki-hosted` or `/cockpit-hosted`
  route; `chat.py` serves only `helpdesk`/`platform`). `COST.md` still counts 3 hosted agents vs 4 declared.
- **Vestigial backend code:** `app/agents/cockpit.py` + `selfwiki.py` (only `*_configured()` over legacy
  fields, never mounted) and `app/agents/secure_search.py` (app-side ACL trim, now out of the production
  `retrieve()` path — kept alive only by tests).
- **Version lag:** `apps/backend/pyproject.toml`, `apps/frontend/package.json` and `app/main.py` all still
  read `0.1.0` (and `title="Foundry Assured"`) while the wiki is `v0.3.0`.
- **azd wiring gap:** `main.parameters.json` doesn't map `appUsersGroupId`, so a plain `azd up` skips the
  `appUsersToFoundry` grant. **api-version skew:** `retrieve()` uses `2026-05-01-preview` vs
  `2025-08-01-preview` in `acl_setup.py`/`secure_search.py`.
- **Doc drift:** `docs/README.md` index omits the new specs/ADRs/plans; `PRESENTATIONS-PORTAL-PLAN.md` is
  cited but still untracked; `lighthouse.bicep` missed the `helpdesk`→`assured` rename.

> **Two gate bugs an earlier dogfood (v0.2.0) surfaced** (the mechanism finding faults in itself);
> both fixed, kept here as history — the v0.3.0 run above scored 100% on all four bundles:
> 1. An extension-alternation regex matched `.js` inside `.json` (`js` sorted before
>    `json`), silently failing every `.json`/`.tsx` citation — unfairly failing the
>    config/frontend-heavy bundles (frontend 37%, infra 50% before the fix). Fixed
>    (longest-extension-first) in `wiki_builder.py`; backend/frontend/infra scores above
>    are post-fix (85–98%).
> 2. ¹ The fidelity check resolved citations only against the bundle's `--repo` gather,
>    but a cross-cutting `docs/` bundle legitimately cites files across `apps/` + `infra/`.
>    Scored against `docs/` alone it read 71%; against the whole monorepo (the fair
>    denominator) it's **85%**. The `--fidelity-root` flag lets a monorepo sub-area
>    resolve citations against the repo root.

## Regenerate

Two paths, both fidelity-gated (≥ 80% of cited paths must resolve to a real file):

**A — Foundry pipeline** (`wiki_builder.py`, uses the Foundry `gpt-5-mini` model → needs `azd up` /
Azure). From `apps/backend/`, one run per area:

```bash
uv run python -m app.knowledge.wiki_builder \
  --repo ../../apps/backend --component foundry-helpdesk-backend --version v0.3.0 \
  --out ../../docs/wiki
# …repeat for ../../apps/frontend, ../../infra, ../../docs
```

**B — Local Agent-Skills path** (**how `v0.3.0` was produced** — **NO Foundry/Azure infra**). The
generator is the upstream Microsoft [`deep-wiki` plugin](https://github.com/microsoft/skills/tree/main/.github/plugins/deep-wiki)
(MIT), **vendored (pinned) at [`.github/skills/deep-wiki/`](../../.github/skills/deep-wiki/)** so any
coding agent that reads `.github/skills` — **GitHub Copilot cloud agent / CLI / VS Code agent mode, or
Claude Code** — discovers it (see [ADR-012](../adr/ADR-012-reuse-upstream-deep-wiki-tooling.md)). Open
the repo in the agent and ask it to *"regenerate the deep-wiki for area X following the
`wiki-page-writer` skill, with linked citations and the ≥80% build-fidelity gate."* Copilot CLI can
also install upstream directly: `/plugin marketplace add microsoft/skills` → `/plugin install
deep-wiki@skills`. (The legacy copy in [`apps/backend/app/knowledge/skills/`](../../apps/backend/app/knowledge/skills/)
is kept for back-compat until callers repoint at the vendored plugin.)

> **Keeping it fresh (roadmap).** The `wiki-freshness` gate only *detects* drift. ADR-012 adds an
> OpenWiki-style regen — [`.github/workflows/wiki-regen.yml`](../../.github/workflows/wiki-regen.yml),
> a manual template — to *close* the loop (drift → regenerate via the skill → PR) once a CI coding
> agent + model credential are wired.

## Ingest into the selfwiki knowledge base

The ingest reuses [`ingest_cockpit.py`](../../apps/backend/app/knowledge/ingest_cockpit.py)
verbatim — only the env points it at the selfwiki names (the mechanism is domain-generic).
No ACL group map → non-blocking ingest, single-audience (this repo is public):

```bash
KB_KNOWLEDGE_SOURCE=selfwiki-docbundles-ks \
KB_DOMAIN_LABEL="o projeto foundry-helpdesk" \
COCKPIT_STORAGE_CONTAINER=selfwiki-corpus \
COCKPIT_SEARCH_KNOWLEDGE_BASE=selfwiki-kb \
COCKPIT_SEARCH_INDEX=selfwiki-docbundles-ks-index \
COCKPIT_DOCBUNDLES=../../docs/wiki \
  uv run python -m app.knowledge.ingest_cockpit
```

The `/selfwiki` agent ([`selfwiki.py`](../../apps/backend/app/agents/selfwiki.py)) then
answers questions about this project grounded in this wiki.
