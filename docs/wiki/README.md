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
(`manifest.json` + `pages/page-N.md` + `llms.txt`):

| Bundle | Source area | Pages | Fidelity (citations → real file) |
| --- | --- | --- | --- |
| `foundry-helpdesk-backend/`  | `apps/backend`  | 7 | 96% (194/203, 36 files) |
| `foundry-helpdesk-frontend/` | `apps/frontend` | 7 | 94% (179/190, 28 files) |
| `foundry-helpdesk-infra/`    | `infra`         | 7 | 98% (132/135, 7 files) |
| `foundry-helpdesk-docs/`     | `docs`          | 7 | 85% (145/170, 30 files)¹ |

> **Two gate bugs this dogfood surfaced** (the mechanism finding faults in itself):
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

From `apps/backend/`, one run per area (paced + fidelity-gated):

```bash
uv run python -m app.knowledge.wiki_builder \
  --repo ../../apps/backend --component foundry-helpdesk-backend --version v0.1.0 \
  --out ../../docs/wiki
# …repeat for ../../apps/frontend, ../../infra, ../../docs
```

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
