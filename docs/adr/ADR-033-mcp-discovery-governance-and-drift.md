# ADR-033 — MCP discovery is governed evidence, not execution

- **Status:** Accepted
- **Date:** 2026-08-31
- **Accepted by:** tech lead/arquiteto, confirmação explícita do desenvolvedor em 2026-08-31
- **Context:** [F03 PRD](../../.smart-coding/20260831-1229-mcp-binding-discovery/02-prd.md)
- **Builds on:** [ADR-009](./ADR-009-native-tool-approval-foundry-connection-resolution.md),
  [ADR-011](./ADR-011-hosted-per-tenant-foundry-toolbox-passthrough.md),
  [ADR-023](./ADR-023-evidence-layer.md),
  [ADR-032](./ADR-032-okf-projections-bindings-and-compensable-publication.md)

## Context

ADR-032 establishes that MCP discovery produces evidence rather than an operational catalogue.
F03 must make that decision executable without duplicating Microsoft Foundry or the Model Context
Protocol, while adding the product controls that those services do not provide: tenant-scoped
administrative classification, sanitized snapshots and blocking drift decisions.

The installed surfaces were checked before this decision:

- `azure-ai-projects` 2.4.0 provides Toolbox `list`, `get`, `list_versions`, `create_version`,
  `delete` and `delete_version` operations;
- `agent-framework` 1.14.0 provides `MCPStreamableHTTPTool`, `allowed_tools`, `approval_mode`,
  request timeouts and `MCPTool.load_tools()`; its source implements discovery with paginated
  `session.list_tools()` calls and does not call `tools/call` on that path;
- Microsoft Learn recommends Foundry Toolboxes, project connections, allowlists and native tool
  approval, and treats remote descriptions, annotations and schemas as untrusted input;
- neither the installed packages, Learn, official samples nor release notes provide a managed
  sanitized snapshot, drift comparison or tenant administrative read/write classification.

The MÁXIMA MAIOR audit returned `PASS`: official capabilities remain the runtime and catalogue
owners; local code is restricted to the identified governance and assurance gaps.

## Decision

### D01 — Discovery is a separate administrative operation

Discovery is synchronous, Admin-only and invokes only MCP initialization and `tools/list` through
the Agent Framework. It never invokes `tools/call`, even for health checks. Each retry is a new
observation rather than an update to an old snapshot.

### D02 — Toolbox and connection identities remain official

Toolboxes and their versions are resolved from the tenant's Foundry project through
`AIProjectClient.toolboxes`. Runtime credentials remain in Foundry project connections, OBO or the
approved public mode. OKF stores references only. The product does not persist a Toolbox catalogue,
resolved token, header or connection credential.

### D03 — Direct endpoints require a distinct approval

A direct endpoint proposal is inert. It cannot access the network before an Admin approves its
exact immutable origin and the egress policy validates it immediately before connection. Endpoint
approval, snapshot review, publication approval and native tool-call approval are distinct,
non-reusable decisions.

For F03, direct endpoints are HTTPS on port 443, redirects are refused and host resolution must
contain only public addresses. Infrastructure egress must independently deny private, loopback,
link-local, reserved and metadata destinations; application DNS validation is defense in depth,
not the sole DNS-rebinding control.

### D04 — Classification is local policy, evidence is immutable

Administrative classification is product policy unavailable in Foundry. Its queryable source is a
tenant-scoped Azure Table owned by `platform_ops`, with an in-memory fake for offline tests.
Decisions use optimistic concurrency and are keyed by tenant, source, tool and tool contract hash.
Every mutation also appends an event to the ADR-023 evidence trail.

Remote metadata can only increase risk. `destructiveHint=true` or `readOnlyHint=false` forces the
effective effect to write; no annotation can authorize read. A missing Admin classification is
`quarantined`. A write classification always retains native approval, and organization policy or
RBAC may still forbid it.

### D05 — Snapshots use Azure-managed immutability and encryption

The normalized and sanitized payload is created once under `mcp-snapshots/{snapshotId}.json` in
the tenant evidence layer. The WORM policy supplies immutability and Azure Storage Service-Side
Encryption supplies AES-256 envelope encryption, using the account's Microsoft-managed key or CMK.
The application implements no cryptographic primitive and never writes unsanitized remote data.

A small Azure Table projection stores only source identity, latest snapshot identity,
`current|stale` state and timestamps. The immutable Blob remains the source of snapshot content;
the audit event stores only the snapshot identity and hash.

### D06 — Canonical hashes isolate drift by tool

Each tool hash is SHA-256 over RFC 8785 JSON Canonicalization Scheme bytes for its sanitized name,
description, input schema, output schema and permitted annotations. The snapshot hash also includes
source identity, resolved Toolbox version, protocol version and tools sorted by name.

Added, removed or contract-changed tools and effective-classification changes are blocking for the
affected tool. Ordering and equivalent object-key ordering are not drift. A default Toolbox version
change blocks binding promotion until Admin review, while already published runtime remains pinned
to its previously reviewed version. Unchanged tools remain available.

### D07 — OKF expresses intent, not authority

`mcp-binding.spec` contains one source (`toolbox` with fixed/default version, or an approved
`endpoint` reference), the intended tool allowlist and a reviewed snapshot reference. URL,
connection, classification and executable state do not appear in the binding. F06 materializes a
default Toolbox selection as a fixed version during publication.

## Consequences

- Foundry and MCP servers remain the operational sources; no parallel catalogue is introduced.
- Discovery can be reviewed and reproduced without executing a remote capability.
- Authorization reads a bounded policy store while every decision remains independently provable.
- Description changes are blocking because remote descriptions influence model behavior.
- Refusing redirects and non-443 endpoints is intentionally conservative; integrations must expose
  a canonical approved HTTPS endpoint.
- Azure Table state and snapshot projection are product code, justified by governance gaps that
  Microsoft services do not currently cover.

## Alternatives refused

- **Trust server annotations:** remote metadata is controlled by the integration being governed.
- **Derive current authorization by scanning the audit Blob:** the evidence stream is append-only
  and unindexed; using it in the hot authorization path is unbounded.
- **Store classification in OKF:** it would let the Builder author its own authority.
- **Implement an MCP client:** Agent Framework already owns protocol negotiation and pagination.
- **Application-level encryption:** Azure Storage already supplies managed envelope encryption;
  custom key and cipher handling would duplicate the platform and enlarge the attack surface.
- **Follow validated redirects:** unnecessary for the first vertical and materially complicates
  credential and DNS-rebinding guarantees.

## Acceptance

Accepted by the developer acting with tech lead/architect authority on 2026-08-31, after explicit
confirmation of the architecture, HTTP contracts, schema, security limits, drift policy,
persistence and observability during `sc-detalhar`.

## Sources

- [Connect agents to MCP server endpoints](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/model-context-protocol)
- [Set up MCP server authentication](https://learn.microsoft.com/azure/foundry/agents/how-to/mcp-authentication)
- [Agent Framework MCP source](https://github.com/microsoft/agent-framework/blob/main/python/packages/core/agent_framework/_mcp.py)
- [Foundry samples](https://github.com/microsoft-foundry/foundry-samples/tree/main/samples/python)
- [Agent Framework releases](https://github.com/microsoft/agent-framework/releases/tag/python-1.14.0)
