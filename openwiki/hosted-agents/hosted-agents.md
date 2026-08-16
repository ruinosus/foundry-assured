---
type: service
title: Hosted Agents
description: "Azure-hosted agent packages and backend bridges, covering Responses and Invocations paths, cached hosted clients, and the capability gaps between hosted and live runtimes."
tags: [hosted, agents, azure-foundry]
---

# Hosted agents

The repository deploys four hosted-agent packages: helpdesk, platform, selfwiki, and techdocs. `azure.yaml` declares each as an `azure.ai.agent` service with a Python startup command. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/azure.yaml#L14-L23) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/azure.yaml#L26-L37) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/azure.yaml#L38-L61)

## Backend bridge responsibilities

The backend bridge in `app/modules/hosted/internal/hosted.py` translates hosted agent protocols into AG-UI-friendly frontend behavior. There are two materially different paths:

- `stream_agui(body, agent_name)` — Responses protocol streaming re-encoded as AG-UI events.
- `stream_platform_agui(body)` — Invocations protocol passthrough intended for platform hosted behavior.

[Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/hosted/internal/hosted.py#L72-L105) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/hosted/internal/hosted.py#L121-L182)

The helpdesk hosted trace is: `/helpdesk-hosted` router → `stream_agui()` → `_client(agent_name)` cached client creation/reuse → `client.responses.create(..., stream=True)` → AG-UI `RunStarted`, text delta, `RunFinished` or `RunError` emission. The platform trace is different: `/platform-hosted` router → `_platform_invocations_url()` → HTTP stream to Foundry Invocations endpoint → relay SSE lines mostly unchanged, except that missing config or request failures synthesize a clean AG-UI `RunErrorEvent`. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/hosted/api.py#L12-L34) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/hosted/internal/hosted.py#L23-L44) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/hosted/internal/hosted.py#L72-L105) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/hosted/internal/hosted.py#L139-L182)

This is why the hosted layer cannot be documented as “just one bridge”.

## Cached client lifecycle

Hosted agent calls share a process-global cache of async clients, project handles, and credentials keyed by agent name. `aclose()` cleans them up at app shutdown. There is an explicit multitenant caveat: the cache currently binds to the first tenant that warms an agent. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/hosted/internal/hosted.py#L18-L24) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/hosted/internal/hosted.py#L23-L44) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/hosted/internal/hosted.py#L47-L56)

## Helpdesk hosted package

`apps/hosted-agent/main.py` packages helpdesk as a hosted Responses agent. Its module comment explicitly documents the capability gap versus the live runtime: it keeps triage/retrieve/resolve and shared grounding, but drops OBO, per-user memory, and HITL escalation because hosted agents are single-identity request/response services. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/hosted-agent/main.py#L1-L16) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/hosted-agent/main.py#L53-L108)

## Platform hosted path and verification limits

The platform hosted bridge is intentionally documented with uncertainty markers in source. `stream_platform_agui()` contains infra-gated TODOs for auth scope, request envelope, and true SSE passthrough framing. In other words, the code knows what it wants to do but does not yet claim full offline verification. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/hosted/internal/hosted.py#L148-L176)

This is matched by hosted-specific tests rather than a claim of complete certainty from static inspection alone.

## Focused tests

Hosted behavior is covered by:

- `tests/hosted/hosted_build_test.py`
- `tests/hosted/hosted_platform_smoke_test.py`
- `tests/hosted/platform_hosted_bridge_test.py`
- `tests/hosted/platform_hosted_e2e_test.py`

Those tests are the first validation wave after changing hosted packages or bridge code.
