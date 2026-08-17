---
type: reference
title: Backend State and Persistence
description: "State ownership map for backend runtime data: memory, tenant records, connections, tickets, hosted client caches, and interrupt/checkpointer durability constraints."
tags: [backend, state, persistence]
---

# Backend state and persistence

This repository does not hide runtime state behind a single generic persistence layer. Different domains own different kinds of state because they have different correctness and lifecycle requirements. This page is the canonical map of those owners.

## Tenant control-plane state

`TenantRecord` is the main persisted control-plane document. It includes tenant identity, lifecycle status, data-plane config, `Connection` references, and enabled domains. It is stored either in-memory for tests/dev or in Azure Table Storage for shared mode. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/tenancy/internal/tenant_store.py#L15-L37) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/tenancy/internal/tenant_store.py#L85-L99) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/tenancy/internal/tenant_store.py#L111-L145)

This state matters before any domain runtime runs. Shared mode cannot resolve tenant-specific services without it.

## Per-user memory state

Helpdesk memory uses `FoundryMemoryProvider`, configured by tenant data-plane settings and scoped with `memory_scope()`. The provider both reads previous facts and stores new ones; it is not a simple cache. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/helpdesk/internal/memory.py#L1-L10) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/helpdesk/internal/memory.py#L27-L40)

The main invariant is scope isolation: in shared mode the key is `tid:oid`, otherwise just `oid`. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/tenancy/internal/tenant_resolution.py#L71-L82)

## Ticket persistence

Tickets are persistent domain outcomes, not transient events. The `/tickets` API surfaces the real tickets opened by approval flows, and in deployed environments they live on Azure Files-backed storage so they survive scale-to-zero. Oncall escalation also writes through `create_ticket`, so helpdesk and oncall share this durable sink. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/tickets/api.py#L9-L15) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/oncall/internal/graph.py#L78-L85)

## Hosted client cache

Hosted-agent bridging uses a process-global `_clients` cache keyed by hosted agent name. Each entry stores an async OpenAI client, project client, and credential. The module also provides `aclose()` and `main.py` calls it during FastAPI shutdown. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/hosted/internal/hosted.py#L18-L24) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/hosted/internal/hosted.py#L23-L44) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/hosted/internal/hosted.py#L47-L56) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/main.py#L48-L55)

The code carries a `TODO(multitenant)` warning: process-global cache binds to the first tenant that warms a hosted agent unless it is later scoped per tenant. That is the main state hazard in hosted bridging. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/hosted/internal/hosted.py#L35-L43)

## Oncall interrupt state

Oncall interrupt/resume state lives in LangGraph’s `InMemorySaver`. That is durable only within one process lifetime. The public module explicitly warns that this is wrong for shared deployment mode, and `oncall_configured()` disables the domain there. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/oncall/internal/graph.py#L21-L24) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/oncall/internal/graph.py#L88-L115) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/oncall/public.py#L10-L14) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/oncall/public.py#L26-L33)

## Operational takeaway

When changing persistence or lifecycle behavior, first decide which state owner you are touching. A bug in tenant resolution, memory poisoning, ticket durability, hosted cache reuse, and graph interrupt loss are different failures with different tests and fixes.
