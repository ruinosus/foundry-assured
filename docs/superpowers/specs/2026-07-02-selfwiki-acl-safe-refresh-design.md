---
title: 'Design: selfwiki ACL-safe refresh + intentional app-users audience'
description: Fix the selfwiki knowledge base so its content refreshes without clobbering the per-document ACL, and make its audience (everyone with app access = the app-users group) intentional instead of an accidental default. Grounded in a read-only diagnosis of the live index.
type: design
audience: contributor
status: draft
updated: 2026-07-02
---

# selfwiki ACL-safe refresh + intentional app-users audience

> **Scope.** The `selfwiki` grounded domain only (this repo's own deep-wiki). The per-user ACL
> machinery it rides on (`acl_setup.py`, `retrieve()`, the `groups` permissionFilter field) is the
> **cockpit** feature and is **working** — this spec does NOT change cockpit behavior except one
> shared hardening (the OBO-header gate). No writes land until this is approved.

## Context — what the live diagnosis found (read-only)

The `--selfwiki` ingest crashed at *create knowledge source* with `Existing field(s) 'groups'
cannot be deleted`. Investigating (all read-only, zero mutation) surfaced the real state:

1. **The selfwiki index is ACL-enabled.** `selfwiki-docbundles-ks-index` has
   `permissionFilterOption='enabled'` and a `groups` field (`permissionFilter='groupIds'`). A search
   without a permission context returns **0** docs; `$count` returns **109**.
2. **All docs are stamped with ONE group = `public` = the app-users group.** An `elevated-read`
   probe showed all 109 docs carry `groups=['SEC-cockpit-kb-public']` (`614eaeb4-…`), which is **the
   same object-ID as `APP_USERS_GROUP_ID`** (the group granted *Foundry User* to use the app,
   `infra/resources.bicep:400` `appUsersToFoundry`). So today **selfwiki is readable by exactly
   "everyone with app access"** — the intended model — but by *accident*: it fell to the ingest
   default (`acl_default_groups='public'`, `acl_setup.py:105`), which merely *happens* to
   equal the app-users group in this tenant.
3. **Content is stale.** All 109 indexed chunks are **v0.2.0**; the `--selfwiki` run uploaded the
   v0.3.0 blobs but crashed before triggering the indexer, so the KB still serves v0.2.0.
4. **selfwiki uses the NATIVE retrieve path.** `domains.py:89` sets `kb_name=selfwiki-si-kb`, so
   `retrieve()` uses `_native_retrieve` (`retrieval.py:66`), not the direct-search fallback (the only
   path that sends `x-ms-enable-elevated-read`). So dev/no-auth selfwiki returns 0.
5. **Latent header bug (RULE #6 hardening).** `_user_search_token(user)` (`retrieval.py:83`) returns
   a token for **any** authed user and `_native_retrieve` attaches `x-ms-query-source-authorization`
   whenever the token is present (`retrieval.py:155`) — it never checks whether the domain is ACL'd.
   The comment claims "ACL domains only"; the code doesn't enforce it. Harmless once selfwiki *is*
   intentionally ACL'd, but wrong for any future public domain.
6. **The re-ingest is unsafe.** `create_knowledge_source` (`ingest_docbundles.py`) re-issues
   `create_or_update_knowledge_source`, which regenerates the index schema **without** `groups` →
   Azure refuses to drop the ACL field. The same call is in the **cockpit** full-ingest path → the
   same latent risk on any re-run over an ACL-stamped index.

## Decision

**selfwiki is a private, single-audience knowledge base whose audience is the app-users group.**
Keep `permissionFilterOption='enabled'`; make the audience **intentional** (bind to
`APP_USERS_GROUP_ID`, not the `public` default); and make the content refresh **ACL-preserving**.

Rationale: the user's model is *"public for whoever has app access."* In Entra terms that is exactly
the app-users group. Binding to it explicitly removes the fragility that `public == app-users` only
by coincidence — in a real company tenant those would be different groups.

## Plan

### A. ACL-safe re-ingest (the crash + the cockpit latent risk)
- In `ingest_selfwiki` (and the cockpit `main()` full path): **do not re-create the blob knowledge
  source when it already exists.** A content refresh only needs: upload blobs → prune stale blobs →
  **purge orphan chunks** → **trigger the indexer**. The KS/index/indexer are provisioning, created
  once. Guard `create_knowledge_source` to *skip when the KS exists* (or catch the
  `field cannot be deleted` conflict and continue), so a refresh never reshapes an ACL-stamped index.
- Revert/rework the merged `--selfwiki` accordingly (it was built for "no ACL" and re-creates the KS).

### B. Intentional app-users audience (make the ACL explicit)
- Give the `selfwiki` `DomainSpec` an `acl_group_map` that resolves the app-users group by name
  (`domains.py`), instead of the current empty map + accidental default. Single-audience: one group.
- Generalize `acl_setup.setup_acl` (today hardcoded to `cockpit_search_index`, lines 92/103) to accept
  the **target index + default group** so it can stamp the **selfwiki** index with the app-users
  group. selfwiki bundles declare no per-doc `groups`, so every doc → the single app-users group
  (intentional, not a fallback). Stays fully "access is DATA" (RULE #6): the group is config data.
- Net object-ID is unchanged (`614eaeb4`), so this is a *formalization*, not a membership change.

### C. OBO-header gate (RULE #6 hardening — shared)
- Attach `x-ms-query-source-authorization` **only when the domain is ACL'd**
  (`getattr(domain, 'acl_group_map', None)` truthy). Gate it in `retrieve()` before calling the
  engines. After B, selfwiki has an `acl_group_map` → it correctly sends the header; a future public
  domain would correctly omit it. Cockpit unchanged.

### D. Content refresh to v0.3.0
- Run the ACL-safe path (A): upload v0.3.0 (already done), prune v0.2.0 blobs, purge v0.2.0 orphan
  chunks, trigger the indexer. Re-stamp via the generalized `setup_acl` (B). KB then serves v0.3.0.

### E. (Optional) dev ergonomics
- Native path returns 0 in dev/no-auth (no header). Either accept (dev needs sign-in) or mirror the
  fallback's `x-ms-enable-elevated-read` on the native path when there is no user token. Low priority.

## Verification
- **Before/after (read-only):** the `elevated-read` probe shows `versions={'0.3.0': …}` and
  `groups=[app-users]` on every doc.
- **In-group user:** an authed member of the app-users group → `retrieve()` returns v0.3.0 docs.
- **Out-of-group / unauth:** returns 0 (fail-closed — correct).
- **Cockpit regression:** the existing A-vs-B ACL round-trip E2E still passes (A reaches confidential,
  B does not) — proves C didn't change cockpit.

## Non-goals / risks / rollback
- **Non-goal:** changing cockpit ACL, group memberships, or making selfwiki public.
- **Risk:** generalizing `setup_acl` touches shared ACL code — covered by the cockpit round-trip E2E.
- **Rollback:** the audience object-ID is unchanged; if B misbehaves, the index already serves the
  same group. permissionFilterOption stays enabled throughout (never a public window).

## Already verified (read-only, this investigation)
- selfwiki index: `permissionFilterOption='enabled'`, `groups` field present, 109 docs, all v0.2.0,
  all stamped `SEC-cockpit-kb-public` (`614eaeb4`) = `APP_USERS_GROUP_ID`.
- selfwiki `retrieve()` with no header → 0 rows (native path); cockpit likewise (correct fail-closed).
- The three ACL groups are the cockpit demo trio (`SEC-cockpit-kb-{public,internal,confidential}`,
  3/2/2 members); `public` doubles as the app-users group in this tenant.
