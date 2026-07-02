---
title: 'Design: rename generic config off the `cockpit` product name'
description: The ACL machinery and the docbundle ingest are prefixed `cockpit_*` but are generic (used by cockpit AND selfwiki, and any future domain). Rename them to neutral names, keeping genuinely cockpit-domain-scoped config as-is, via a NON-breaking alias migration.
type: design
audience: contributor
status: draft
updated: 2026-07-02
---

# Rename generic config off the `cockpit` product name

> **Why now.** `cockpit` is a **product/domain**, but a chunk of GENERIC machinery wears its name
> because cockpit was the first grounded domain built. Now that the ACL + docbundle-ingest are
> reused by **selfwiki** (and are the reusable pattern), the `cockpit_*` prefix on the generic parts
> is misleading. This spec scopes the rename tightly and migrates **without breaking** deployments
> (env vars, repo variables, azd env, container env) — extra important after the recent
> APP_USERS_GROUP_ID regression from moving fast.

## Keep vs rename (the key distinction)

**KEEP — genuinely cockpit-*domain*-scoped** (each grounded domain has its own mirror; `selfwiki_*`
already exists as the twin, so this is correct per-domain naming):

- `cockpit_search_knowledge_base`, `cockpit_search_index`, `cockpit_storage_container`,
  `cockpit_searchindex_knowledge_base`, `cockpit_searchindex_knowledge_source`,
  `cockpit_docbundles_path`, `cockpit_hosted_agent_name` — the **cockpit domain's** resources.

**RENAME — generic machinery wearing a product name:**

| Today (generic, cockpit-named) | Proposed neutral name | What it is |
|---|---|---|
| `COCKPIT_ACL_GROUP_MAP` / `cockpit_acl_group_map` | `ACL_GROUP_MAP` | tenant group registry (name→objectID) |
| `COCKPIT_ACL_PUBLIC_GROUP` | `ACL_PUBLIC_GROUP` | group id for the name "public" |
| `COCKPIT_ACL_INTERNAL_GROUP` | `ACL_INTERNAL_GROUP` | "internal" |
| `COCKPIT_ACL_CONFIDENTIAL_GROUP` | `ACL_CONFIDENTIAL_GROUP` | "confidential" |
| `COCKPIT_ACL_DEFAULT_GROUPS` | `ACL_DEFAULT_GROUPS` | default read groups (fail-closed if empty) |
| `COCKPIT_ACL_CLASSIFICATION` | `ACL_CLASSIFICATION` | path to the `{doc:[group]}` map |
| module `app/knowledge/ingest_cockpit.py` | `app/knowledge/ingest_docbundles.py` | the **generic** docbundle→KB ingest (serves cockpit AND selfwiki) |

`acl_group_map` (the parsed property on `TenantConfig`) already has a neutral name — good; it just
reads the renamed fields.

**Undecided (call it out, decide in review):** `COCKPIT_DOCBUNDLES` / `KB_KNOWLEDGE_SOURCE` /
`KB_DOMAIN_LABEL` are ingest CLI overrides. `KB_*` are already neutral; `COCKPIT_DOCBUNDLES` overlaps
with the cockpit-scoped `cockpit_docbundles_path` — likely fold into a neutral `DOCBUNDLES_DIR` on the
generic ingest. Minor.

## Non-goals

- **Not** renaming the cockpit **domain** itself (`/cockpit`, the `cockpit` DomainSpec, its
  KB/index/container) — cockpit is a real product/domain.
- **Not** renaming the Entra **groups** (`SEC-cockpit-kb-public/internal/confidential`) — those live
  in the customer tenant; renaming them is a tenant-admin action + a config value change, separate
  from code. (Note: `SEC-cockpit-kb-public` currently doubles as `APP_USERS_GROUP_ID` — see the
  selfwiki-acl spec; a dedicated `SEC-<product>-app-users` group would be cleaner but is tenant-side.)

## Migration — NON-breaking (alias, then deprecate)

A flat rename of env vars is a breaking flag-day across `.env`, **repo variables**, **azd env**,
the **container env** (`containerapps.bicep` + `main.parameters.json`), `infra/main.bicep`, the
tenant store defaults, tests, and docs. Instead:

1. **Config reads BOTH names (new preferred, old fallback).** `_TenantEnv` is pydantic-settings, so
   use `Field(validation_alias=AliasChoices("acl_public_group", "cockpit_acl_public_group"))` (verify
   the exact pydantic-settings API — RULE #1) so `ACL_PUBLIC_GROUP` wins and `COCKPIT_ACL_PUBLIC_GROUP`
   still works. **No deployment breaks.**
2. **Module rename with a shim.** Move the code to `ingest_docbundles.py`; keep
   `ingest_cockpit.py` as a thin re-export (`from .ingest_docbundles import *  # deprecated`) for one
   release so any scripts/CI/docs (`python -m app.knowledge.ingest_cockpit`) keep working; update
   in-repo callers to the new module.
3. **Update surfaces to the NEW names** (non-breaking, since aliases cover the old): `.env.example`,
   `infra/*` env wiring, repo variables (add new, keep old until step 5), docs, the wiki bundles.
4. **Deprecation window** — one release with both names + a log warning when an old-name env is read.
5. **Drop the old names** in a later release once no deployment sets them.

## Blast radius

~18 files touch `cockpit` today (backend `app/core/tenant.py`, `app/knowledge/{acl_setup,ingest_cockpit}.py`,
`app/domains.py`, tests under `eval/`; infra `containerapps.bicep`/`main.bicep`/`main.parameters.json`;
docs). With the alias approach the code change is mechanical and covered by the existing **cockpit
A-vs-B ACL round-trip E2E** (must stay green) + the ingest smoke.

## Verification

- Backend imports + `setup_acl`/ingest unit paths pass with **only new** names set, and with **only
  old** names set (alias fallback), and with **both**.
- Cockpit ACL round-trip E2E green (unchanged behavior).
- `python -m app.knowledge.ingest_cockpit --selfwiki` still runs (shim) and `--selfwiki` via the new
  module runs.

## Sequencing

Do this **after** the current fixes settle (selfwiki ACL #86, deploy wiring #92). It's a hygiene
refactor — no user-facing behavior change — so it can land on `develop` and ride the next release.
