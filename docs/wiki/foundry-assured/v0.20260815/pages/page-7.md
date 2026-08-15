The `platform` domain is the outlier in the backend registry. Unlike `helpdesk`, it is not a multi-agent workflow, and unlike `cockpit` or `selfwiki`, it does not answer from retrieved documents. It is a tool-driven concierge intended to operate over Microsoft-first-party MCP servers and to preserve approval semantics for state-changing actions.[`apps/backend/app/domains.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/app/domains.py#L3-L6) [`apps/backend/app/domains.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/app/domains.py#L98-L99) [`apps/hosted-platform/main.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/hosted-platform/main.py#L3-L21)

The detailed serving pattern for the live route is documented in platform-per-request-agent.md: platform must rebuild tenant config, caller roles, and OBO-sensitive tools per request rather than mount one eager agent forever.

## Mounting behavior

The live platform route is mounted only when `platform_configured()` returns true. The registry does not synthesize a fallback agent here; it simply avoids mounting the route when the platform domain is not configured.[`apps/backend/app/domains.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/app/domains.py#L152-L165)

The domain depends on `_domain_deps("platform")`, so in shared mode it inherits both authentication and per-tenant domain entitlement gating.[`apps/backend/app/domains.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/app/domains.py#L102-L108) [`apps/backend/app/api/chat.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/app/api/chat.py#L29-L34)

## Live versus hosted split

The repository treats platform as two related but different paths:

- **live**: mounted directly as an AG-UI endpoint backed by `platform_agent_proxy`, rebuilt per request so tool access can reflect the caller’s roles and OBO credential.[`apps/backend/app/domains.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/app/domains.py#L152-L165)
- **hosted**: exposed through `/platform-hosted`, which calls `stream_platform_agui()` and is meant to bridge the deployed hosted platform agent over the Invocations protocol.[`apps/backend/app/api/chat.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/app/api/chat.py#L29-L34) [`apps/backend/app/services/hosted.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/app/services/hosted.py#L121-L182)

That split matters because the hosted path is explicitly more infra-gated and less verified offline than the live path.

## Hosted bridge constraints

`stream_platform_agui()` is intentionally honest about its unknowns. It computes an Invocations URL from the tenant’s Foundry project endpoint and hosted agent name, acquires a token for `https://ai.azure.com/.default`, forwards the caller’s AG-UI run body as-is, and attempts to relay server-sent events without re-encoding them.[`apps/backend/app/services/hosted.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/app/services/hosted.py#L107-L118) [`apps/backend/app/services/hosted.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/app/services/hosted.py#L121-L177)

But the code also records three explicit infra-gated uncertainties:

- the exact Foundry data-plane scope is best-evidence, not SDK-pinned offline.[`apps/backend/app/services/hosted.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/app/services/hosted.py#L148-L151)
- the request body shape expected by Invocations is not fully verified offline.[`apps/backend/app/services/hosted.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/app/services/hosted.py#L153-L166)
- `aiter_lines()` probably corrupts byte-identical AG-UI framing and likely needs `aiter_bytes()` or similar once validated against a deployed agent.[`apps/backend/app/services/hosted.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/app/services/hosted.py#L168-L177)

Those TODOs are part of the current design, not cleanup noise. Any change that claims full parity must resolve them against deployed evidence.

## Hosted platform packaging seam

The hosted platform container also documents its deploy-time seams explicitly. It uses `InvocationsHostServer`, not `ResponsesHostServer`, and it expects tools to be configured on a Foundry Toolbox referenced by `TOOLBOX_NAME`. The container deliberately does not rebuild live per-request tools or hand-roll credentials.[`apps/hosted-platform/main.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/hosted-platform/main.py#L16-L21) [`apps/hosted-platform/main.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/hosted-platform/main.py#L54-L64) [`apps/hosted-platform/main.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/hosted-platform/main.py#L72-L77)

That creates a firm ownership boundary:

- live platform tool filtering and user-bound auth live in the backend runtime
- hosted platform tool availability is deploy-time data on the Foundry Toolbox

## Behavioral invariants

Safe changes to platform must preserve these invariants:

1. writes must remain approval-gated rather than claimed optimistically in prompt text alone.[`apps/hosted-platform/main.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/hosted-platform/main.py#L35-L41)
2. hosted platform must stay separate from Responses-based grounded twins because it needs interrupt-capable protocol behavior.[`apps/hosted-platform/main.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/hosted-platform/main.py#L3-L14)
3. tenant domain entitlement must continue to gate hosted and live paths equally.[`apps/backend/app/domains.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/app/domains.py#L102-L108) [`apps/backend/app/api/chat.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/app/api/chat.py#L29-L34)

## Focused tests

The highest-value current tests for this area are:

- `eval/platform_hosted_bridge_test.py` for the hosted bridge’s clean error envelope when infra is unavailable.[`apps/backend/eval/platform_hosted_bridge_test.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/eval/platform_hosted_bridge_test.py#L1-L18)
- `eval/platform_hosted_e2e_test.py` and `eval/hosted_platform_smoke_test.py` for deploy-time or smoke-level validation of the hosted path.[`apps/backend/eval/platform_hosted_e2e_test.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/eval/platform_hosted_e2e_test.py#L1-L58) [`apps/backend/eval/hosted_platform_smoke_test.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/eval/hosted_platform_smoke_test.py#L1-L56)
- `eval/rbac_per_tool_test.py` and `eval/mcp_brokering_e2e_test.py` for per-tool role and brokering semantics that inform live platform behavior.[`apps/backend/eval/rbac_per_tool_test.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/eval/rbac_per_tool_test.py#L1-L64) [`apps/backend/eval/mcp_brokering_e2e_test.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/eval/mcp_brokering_e2e_test.py#L1-L62)

## Minimal validation

- `cd apps/backend && uv run python -m eval.platform_hosted_bridge_test`
- `cd apps/backend && uv run python -m eval.rbac_per_tool_test`

These are the narrowest checks that cover hosted envelope safety and one key live-tool authorization invariant.