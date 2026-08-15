# Hosted platform agent

The hosted platform agent is implemented in [`apps/hosted-platform/main.py`](../../apps/hosted-platform/main.py). It is the most distinctive hosted container because it targets **Invocations**, not Responses.

## Why it uses Invocations

The source comments explain the design intent clearly:

- platform is a tool-driven concierge,
- it needs write-approval interrupts to round-trip on the hosted path,
- Responses is insufficient for that goal,
- Invocations is treated as the raw AG-UI-compatible hosted protocol.

This makes hosted platform the parity-oriented hosted path, not a deliberately stripped-down twin like hosted grounded agents.

## Runtime entrypoint

`main()`:

- creates `DefaultAzureCredential()`
- builds a `FoundryChatClient`
- reads `TOOLBOX_NAME` from the environment
- creates the `PlatformConcierge` agent with `default_options={"store": False}`
- serves it using `InvocationsHostServer(agent)`

## Toolbox binding model

A critical design rule recorded in the source is that hosted platform tools are **not** built per request in the container.

Instead:

- tools are configured on the Foundry Toolbox at deploy time,
- OAuth identity passthrough is data on the toolbox or connection,
- the hosted container should reference the toolbox by name,
- it should not call the live per-request `build_mcp_tools()` path,
- it should not hand-roll credentials for tool access.

This keeps hosted tool configuration aligned with the repository's broader rule that connection and authorization shape should live in data, not code branches.

## Prompt contract

`PLATFORM_INSTRUCTIONS` is inlined as a mirror of the live prompt constant. It directs the agent to:

- prefer connected tools over guessing,
- ground factual claims in tool results,
- state when a required tool is unavailable,
- never claim it performed a write action itself,
- let the approval step handle actual state changes.

That last point is the hosted-prompt analogue of the live approval contract.

## Infra-gated TODOs are part of the current design

The file intentionally carries TODOs marking what is not yet offline-verified:

- exact toolbox-to-hosted-agent binding mechanics,
- exact `InvocationsHostServer` constructor behavior in the hosted image,
- exact deployed protocol details that only the hosted environment can prove.

These are not accidental loose ends. They define the current boundary between repository-known behavior and deploy-time verification.

## Backend bridge relationship

The live frontend reaches hosted platform through backend `stream_platform_agui()` in `app/services/hosted.py`.

That bridge assumes the hosted endpoint can be relayed as AG-UI SSE. It also carries infra-gated TODOs about:

- token scope,
- request body shape,
- byte-preserving SSE passthrough.

So hosted platform changes should often be reviewed together with the backend bridge. That bridge still guarantees a clean failure envelope: if no endpoint is configured or another bridge error occurs, `stream_platform_agui()` emits `RunStartedEvent`, `TextMessageStartEvent`, `TextMessageEndEvent`, and `RunErrorEvent` so the frontend sees a normal AG-UI error shape rather than a broken stream.

Current validation is split deliberately:

- `platform_hosted_bridge_test.py` proves the clean offline error envelope,
- `hosted_platform_smoke_test.py` proves the scaffold declares Invocations,
- `platform_hosted_e2e_test.py` documents that full live contract verification is still deferred to deployed infrastructure.

## Tests

Representative tests:

- `platform_hosted_bridge_test.py`
- `platform_hosted_e2e_test.py`
- `hosted_platform_smoke_test.py`
- `mcp_brokering_e2e_test.py` for adjacent tool-brokering assumptions

## Related pages

- Hosted agents overview
- Platform domain
- Automation and release
