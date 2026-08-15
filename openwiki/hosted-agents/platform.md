---
type: deployment-guide
title: Hosted platform agent
description: Invocations-based hosted platform packaging, toolbox binding seam, deploy-time configuration, and the unresolved infra-verified details that still constrain safe changes.
tags: [hosted-agents, platform, invocations, toolbox]
---

The hosted platform agent is the most specialized hosted app in the repo. It exists because platform’s write-approval and tool-driven model need the Invocations protocol rather than the simpler Responses protocol used by grounded twins.[`apps/hosted-platform/main.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/hosted-platform/main.py#L1-L14)

## Entrypoint and server type

`main.py` creates a `FoundryChatClient`, constructs one platform concierge agent, and serves it with `InvocationsHostServer`. That server choice is the defining trait of this app.[`apps/hosted-platform/main.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/hosted-platform/main.py#L45-L52) [`apps/hosted-platform/main.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/hosted-platform/main.py#L72-L77)

## Toolbox binding seam

Unlike the live platform path, which can rebuild tools per request, the hosted app delegates tool configuration to deploy-time Foundry Toolbox setup. `TOOLBOX_NAME` is read from env, and comments explicitly say the app must not call the live `build_mcp_tools()` path or hand-roll credentials inside the container.[`apps/hosted-platform/main.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/hosted-platform/main.py#L54-L64)

This is the main extension seam for hosted platform deployment: changes to tool availability or auth brokering belong in Toolbox and connection configuration, not in this runtime file.

## Deploy-time config surface

The hosted platform app depends on:

- `FOUNDRY_PROJECT_ENDPOINT`
- `AZURE_AI_MODEL_DEPLOYMENT_NAME`
- `TOOLBOX_NAME`

and authenticates as the hosted platform identity via `DefaultAzureCredential`.[`apps/hosted-platform/main.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/hosted-platform/main.py#L45-L52) [`apps/hosted-platform/main.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/hosted-platform/main.py#L54-L58)

## Known infra-gated uncertainties

The source intentionally leaves some behavior unresolved until validated against deployed infrastructure:

- exact Toolbox-to-hosted-agent binding details are still TODOs.[`apps/hosted-platform/main.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/hosted-platform/main.py#L60-L64)
- even the `InvocationsHostServer` constructor signature is marked as infra-gated because the dependency is not offline-verified in the backend venv.[`apps/hosted-platform/main.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/hosted-platform/main.py#L72-L75)
- the backend bridge still has SSE framing and request-envelope TODOs for the hosted platform path.[`apps/backend/app/services/hosted.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/app/services/hosted.py#L153-L177)

## Runtime consumer in backend

The backend’s `/platform-hosted` endpoint is the consumer-facing bridge for this app. It calls `stream_platform_agui()`, which is intended as a byte-preserving pass-through for AG-UI SSE from the Invocations endpoint, falling back to a clean `RunErrorEvent` on failure.[`apps/backend/app/api/chat.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/app/api/chat.py#L29-L34) [`apps/backend/app/services/hosted.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/app/services/hosted.py#L121-L182)

## Focused tests

- `eval/platform_hosted_bridge_test.py` for hosted platform bridge envelope behavior without live infra.[`apps/backend/eval/platform_hosted_bridge_test.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/eval/platform_hosted_bridge_test.py#L1-L18)
- `eval/platform_hosted_e2e_test.py` and `eval/hosted_platform_smoke_test.py` for broader hosted platform validation when infra exists.[`apps/backend/eval/platform_hosted_e2e_test.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/eval/platform_hosted_e2e_test.py#L1-L58) [`apps/backend/eval/hosted_platform_smoke_test.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/eval/hosted_platform_smoke_test.py#L1-L56)

## Minimal validation

- `cd apps/backend && uv run python -m eval.platform_hosted_bridge_test`

That check is the narrowest trustworthy signal while the deploy-time path remains partly infra-gated.