---
type: service
title: Grounded Domains
description: "Grounded question-answering domains such as selfwiki and techdocs, including the shared archetype, per-domain configuration, retrieval path, and declarative instruction ownership."
tags: [backend, grounded, retrieval, citations]
---

# Grounded domains

The backend’s grounded domains are `techdocs` and `selfwiki`. In the registry they are `kind: "grounded"` domains that resolve per-request tenant config and stream cited Q&A through the common `stream_grounded` archetype. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/registry.py#L73-L75) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/registry.py#L96-L132) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/registry.py#L137-L160)

## Shared archetype

`app/modules/grounded/public.py` exposes the public API for grounded behavior: `stream_grounded`, synthesis helpers, knowledge configuration checks, and `PerRequestAgent`. The module docstring states the core product rule: every answer produced here must carry at least one source citation, enforced by eval policy rather than by transport protocol. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/grounded/public.py#L1-L9) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/grounded/public.py#L11-L33)

That separation matters: the transport can stream anything, but repository assurance requires citations and evaluates them independently.

## Per-domain configuration

The registry’s `DomainSpec` enforces that a grounded domain must define either a knowledge base name or a search index. `_domains()` then fills those fields from tenant config, plus instructions and ACL group maps. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/registry.py#L33-L59) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/registry.py#L96-L132)

`selfwiki` is notable because it uses an app-users ACL map when `APP_USERS_GROUP_ID` is present, making the repository wiki a private grounded corpus by default. `techdocs` instead uses tenant-configured KB/index/ACL values. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/registry.py#L108-L129)

## Declarative instruction ownership

Grounded domain instructions are not authored in the registry itself. `_domains()` imports `TECHDOCS_INSTRUCTIONS` and `SELFWIKI_INSTRUCTIONS` from `app.modules.agentdefs.public`, which means changes to grounding behavior often start in declarative agent-definition assets under `apps/backend/agents/`, not in the registry. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/registry.py#L96-L99) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/agentdefs/internal/definitions.py#L24-L35) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/agentdefs/internal/definitions.py#L140-L155)

That is the main extension seam for adding another grounded domain: define the prompt assets, export instructions, then add the `DomainSpec` row.

## Retrieval and ACL path

Grounded domains depend on the knowledge module’s retrieval path and ACL guarantees. The repository’s retrieval ACL parity test explains the seam precisely: the production `retrieve()` path must preserve per-user trimming through header attachment, native retrieval, docKey parsing, and deduplication. The test asserts that a confidential source appears for an entitled user A and does not appear for public-only user B. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/tests/knowledge/retrieval_acl_parity_test.py#L1-L18) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/tests/knowledge/retrieval_acl_parity_test.py#L104-L142)

The request flow is:

1. `_mount_grounded()` captures `current_user()` before entering `StreamingResponse`, because the contextvar would otherwise be lost inside the stream generator.
2. `stream_grounded()` receives the request payload, domain spec, and captured user.
3. The grounding layer calls `retrieve()` with that user and domain.
4. Retrieval chooses native KB retrieve when a knowledge base is configured, otherwise direct search fallback.
5. The synthesis layer emits AG-UI/SSE events: a run-start event, assistant text-delta events, and a custom `sources`/evidence event carrying the citations/snippets that the right-hand evidence panel renders.

[Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/registry.py#L137-L154) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/knowledge/internal/retrieval.py#L48-L73) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/knowledge/internal/retrieval.py#L105-L170)

Per-user search authorization is attached only when a user-scoped token is available and the domain is ACL-sensitive: `_user_search_token(user)` is called only when `acl_group_map` is truthy, the native/direct-search headers carry `x-ms-query-source-authorization` only when that token exists, and ACL domains intentionally fail closed to zero docs when no user token can be attached. Public domains omit that header and run under app identity, while direct-search dev/public fallback can use elevated read instead of ACL trimming. Dedupe and 1-based reindexing are centralized in `_project()` and locked in by `retrieval_shape_test`, while A-vs-B visibility is locked in by `retrieval_acl_parity_test`. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/knowledge/internal/retrieval.py#L64-L73) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/knowledge/internal/retrieval.py#L81-L102) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/knowledge/internal/retrieval.py#L157-L163) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/knowledge/internal/retrieval.py#L248-L275) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/knowledge/internal/retrieval.py#L278-L295) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/tests/knowledge/retrieval_acl_parity_test.py#L107-L142)

The important repository invariant is therefore: **ACL trimming is a pre-answer retrieval property, not a postprocessing embellishment**.

## Selfwiki vs TechDocs

The two grounded domains differ mainly by corpus:

- **selfwiki** is grounded in this repo’s own generated wiki/docbundle content and usually exposed as a private audience to app users.
- **techdocs** is grounded in a separate TechDocs corpus and can be temporarily hidden in the frontend even while backend support remains. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/frontend/lib/domains.ts#L47-L64) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/frontend/lib/domains.ts#L65-L79)

The shared archetype means adding a new grounded domain should usually not require new streaming logic, only new configuration, prompts, and corpus ingest.

## Focused tests

Key tests for grounded behavior include:

- `tests/knowledge/retrieval_acl_parity_test.py`
- `tests/knowledge/retrieval_shape_test.py`
- `tests/knowledge/techdocs_acl_stamp_test.py`
- grounded payload/native snippet/per-request override tests under `tests/grounded/`

After changing grounded domain config, retrieval, or citation behavior, start there.
