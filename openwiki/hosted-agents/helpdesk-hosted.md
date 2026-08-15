---
type: hosted-agent-page
title: Hosted helpdesk agent
description: Foundry-hosted packaging of the helpdesk workflow, including what it preserves from the live workflow and what it deliberately drops.
tags: [hosted-agents, helpdesk, workflow]
---

# Hosted helpdesk agent

The hosted helpdesk agent is implemented in [`apps/hosted-agent/main.py`](../../apps/hosted-agent/main.py). It packages a simplified version of the helpdesk workflow as a Foundry hosted agent served through `ResponsesHostServer`.

## Runtime entrypoint

`main()`:

- creates `DefaultAzureCredential()`,
- builds a `FoundryChatClient` from `FOUNDRY_PROJECT_ENDPOINT` and `AZURE_AI_MODEL_DEPLOYMENT_NAME`,
- builds `AzureAISearchContextProvider` from `AZURE_SEARCH_ENDPOINT` and `AZURE_SEARCH_KNOWLEDGE_BASE`,
- constructs triage, retrieve, and resolve `AgentExecutor`s,
- builds a workflow and converts it to an agent,
- serves it with `ResponsesHostServer`.

## Workflow shape

The hosted workflow mirrors the logical shape of live helpdesk:

- `triage`
- `retrieve`
- `resolve`

It uses `context_mode="last_agent"` so each step sees the previous step's output, matching the live pipeline's chaining semantics.

## Deliberate feature drops

The source comments are explicit that this is a self-contained, single-identity variant. It **drops**:

- OBO caller identity,
- per-user memory,
- human-in-the-loop escalation,
- the live AG-UI workflow step streaming experience.

Those are not accidental omissions. They are features tied to the live backend's request-scoped AG-UI workflow runtime.

## Why the hosted helpdesk still matters

Even without those features, the hosted helpdesk agent proves that the core triage-retrieve-resolve workflow can be packaged as a managed hosted agent invoked over the Foundry gateway.

This supports:

- phase-6 hosted deployment,
- cost-efficient idle behavior,
- deployment into Foundry Agent Service as a managed unit.

## Search grounding

The hosted agent still grounds against the same general Foundry IQ knowledge-base model used by the live app:

- `AzureAISearchContextProvider`
- `mode="agentic"`

So it preserves the high-level knowledge path even while dropping live-user features.

## Output contract

The workflow is wrapped with `output_from=[resolve]`, which means only the resolve step's final answer becomes the agent's final output.

This is appropriate for a Responses-style hosted agent because intermediate AG-UI workflow rendering is not the primary contract there.

## Relationship to backend hosted bridge

The frontend does not talk to this hosted agent directly. Instead, backend `POST /helpdesk-hosted` calls `stream_agui(body, tenant_config().hosted_agent_name)` in `app/services/hosted.py`, which re-emits Responses output as AG-UI SSE so the same CopilotKit UI can render it.

## Focused tests

Relevant tests include:

- `hosted_build_test.py`
- `grounded_deployed_roundtrip_test.py` for deployed hosted behavior adjacent to hosted runtime paths
- `platform_hosted_bridge_test.py` for shared backend bridge patterns

## Related pages

- [Hosted agents overview](overview.md)
- [Helpdesk workflow](../backend/helpdesk-workflow.md)
- [Backend domains and endpoints](../backend/domains-and-endpoints.md)
