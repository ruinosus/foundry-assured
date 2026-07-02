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

## Migration — DIRECT rename, no back-compat (decided 2026-07-02)

The initial plan kept the old names via `AliasChoices` + a module shim (a deprecation window). On
review we chose a **direct rename instead** — remove the old names outright — because they were set in
only a few places, none of them the running app:

- the developer's local `.env` (updated in this change),
- three **dormant repo variables** (`COCKPIT_ACL_*`) that `deploy.yml` never wires into the deploy env,
- `infra/entra/create-acl-identities.sh` (which just *prints* `.env` lines — updated here),

and the **deployed backend never set `COCKPIT_ACL_*`** (they're not in the container env). So dropping
them breaks nothing in production.

Done in this change:
1. **Config** — `_TenantEnv` fields are plain `acl_*` (env `ACL_PUBLIC_GROUP`, `ACL_INTERNAL_GROUP`,
   `ACL_CONFIDENTIAL_GROUP`, `ACL_DEFAULT_GROUPS`, `ACL_CLASSIFICATION`). `acl_extra_group_map` keeps a
   single `validation_alias="acl_group_map"` (its env is `ACL_GROUP_MAP`; the field name differs to avoid
   the `acl_group_map` **property**). **No `COCKPIT_ACL_*` fallback.**
2. **Module** — `ingest_cockpit.py` → `ingest_docbundles.py`; the compat shim was **removed** (callers
   use `python -m app.knowledge.ingest_docbundles`).
3. **Surfaces** — `.env.example`, `infra/entra/*` (script + bicep comment), the dev `.env`, docs, and the
   eval probes updated to `ACL_*`. The three dormant `COCKPIT_ACL_*` repo variables are renamed to `ACL_*`.

## Verification (done)

- Backend compiles + imports; `setup_acl`/ingest paths use `acl_*`; no `cockpit_acl_<field>` residue in code.
- 3-way env probe: `ACL_PUBLIC_GROUP` (new) → used; `COCKPIT_ACL_PUBLIC_GROUP` (old, `_env_file=None`) →
  **ignored** (no alias) — confirmed.
- `python -m app.knowledge.ingest_docbundles [--selfwiki]` runs.
- The cockpit A-vs-B ACL round-trip E2E is the behavioral guard (must stay green in CI).

## Sequencing

Do this **after** the current fixes settle (selfwiki ACL #86, deploy wiring #92). It's a hygiene
refactor — no user-facing behavior change — so it can land on `develop` and ride the next release.
