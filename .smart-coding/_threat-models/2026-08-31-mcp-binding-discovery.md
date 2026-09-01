# Threat model — MCP binding discovery

- **Date:** 2026-08-31
- **Scope:** F03 `mcp-binding`, Toolbox projection, direct endpoint approval, MCP `tools/list`,
  classification, snapshot, drift and conformity
- **Method:** STRIDE, informed by NORDOR-122, NORDOR-107 and POLDOR-015
- **Status:** Proposed; security and architecture review required before implementation

## Assets and trust boundaries

### Protected assets

- tenant identity and Foundry project association;
- Toolbox, connection and endpoint identities;
- OBO tokens and credentials resolved from Foundry connections;
- administrative classifications and approvals;
- sanitized discovery snapshots and their hashes;
- runtime allowlists and native approval settings;
- network access of the backend and its managed identity.

### Trust boundaries

1. Browser/caller to authenticated authoring API.
2. Authoring API to tenant resolution and policy stores.
3. Backend to Foundry control plane and tenant project.
4. Backend to an untrusted remote MCP endpoint.
5. Platform modules to tenant evidence storage.
6. Application egress validation to infrastructure network enforcement.

Remote MCP names, descriptions, annotations, schemas, protocol errors and DNS answers are
untrusted. An Admin approval does not make remote content trusted; it permits one exact origin to
be contacted under the remaining controls.

## Data flow

1. Builder selects a tenant-visible Toolbox or proposes an inert direct endpoint.
2. Admin approves the exact direct endpoint without initiating network access.
3. Discovery resolves tenant, source and connection; obtains a per-source lease.
4. Egress policy validates scheme, port, hostname and all DNS answers immediately before connect.
5. Agent Framework performs MCP initialization and paginated `tools/list` only.
6. The response is bounded, parsed, allowlisted, redacted and canonicalized in memory.
7. The sanitized snapshot is written once to tenant evidence Blob; an audit event records its hash.
8. Admin classifications are stored with optimistic concurrency and independently audited.
9. Conformity compares reviewed and current hashes before publication or execution.

## STRIDE analysis

| Category | Threat | Control | Verification |
|---|---|---|---|
| Spoofing | Caller supplies another tenant/project | Tenant comes only from authenticated context; request has no tenant/project field; cross-tenant lookup is 404 | Two-tenant negative integration tests |
| Spoofing | DNS changes after approval or validation | Exact immutable host approval, resolution before every connect, public-IP-only answers, no redirects, infrastructure egress deny for private/metadata ranges | DNS rebinding fake plus deployed egress test |
| Spoofing | Connection name resolves outside tenant | Resolve through current tenant's Foundry project and tenant-local connection records only | Same-name connections in two tenants |
| Tampering | Server changes tool schema/description after review | RFC 8785 + SHA-256 per tool; blocking drift and quarantine before call | Addition/removal/description/schema/annotation cases |
| Tampering | Concurrent Admin updates overwrite policy | Azure Table ETag/revision and `expectedRevision`; conflict returns 409 | Concurrent update test |
| Tampering | Snapshot is replaced | Create-once Blob under WORM policy; hash-chained audit reference | Duplicate create and integrity verification |
| Repudiation | Admin denies endpoint/classification/review decision | Separate audit event with actor, time, decision, reason, resource and hash | Audit receipt and chain gate |
| Repudiation | One approval is reused for another purpose | Endpoint approval, snapshot review, publication and tool-call approval have distinct types and references | Replay/cross-purpose negative tests |
| Information disclosure | Token/header enters OKF, logs or snapshot | Strict recursive secret-key rejection; credentials resolved in memory; structural redaction before first durable write; content-free telemetry | Canary token tests across API, logs, Blob and errors |
| Information disclosure | Remote metadata leaks cross-tenant | Tenant-scoped Blob/Table clients and keys; pseudonymized telemetry; cross-tenant resource is indistinguishable from missing | Two-tenant snapshot tests |
| Information disclosure | Auth header follows redirect | Redirects refused; direct URLs cannot contain userinfo; public mode sends no auth header | 30x and header-capture server tests |
| Denial of service | Huge/deep tool catalogue exhausts CPU/memory | 200 tools, 256 KiB snapshot, 32 KiB/schema, depth 12, 200 properties, bounded strings; no partial snapshot | Boundary and over-limit tests |
| Denial of service | Slow endpoint occupies workers | 5 s connect, 10 s request/read, 15 s total; one tenant+source lease for 30 s; excess is 429 | Timeout and concurrent discovery tests |
| Denial of service | Pagination never terminates or repeats cursor | Global tool/byte/time limits and repeated-cursor rejection | Malicious pagination fake |
| Elevation of privilege | Server labels write tool as read | Remote metadata never grants read; destructive/write hints only elevate; Admin decision required | Conflicting annotation/classification matrix |
| Elevation of privilege | Builder embeds classification or credential | Those fields are absent from strict `mcp-binding`; unknown fields and secret-like keys fail | OKF schema contract tests |
| Elevation of privilege | Discovery calls a side-effecting tool | Discovery adapter exposes only initialize and `load_tools`/`tools/list`; `call_tool` fake fails the test | No-`tools/call` integration gate |
| Elevation of privilege | Write executes without native approval | Runtime derives `allowed_tools` and approval mode from conformity; writes always require native approval and role/policy may still forbid | Approval parity and pre-call denial tests |

## Security invariants

1. No network request occurs for an unapproved direct endpoint.
2. No discovery or health path invokes `tools/call`.
3. No remote field can lower effective risk.
4. No unclassified or drifted tool enters a runtime allowlist.
5. No credential or unsanitized remote payload reaches durable storage or telemetry.
6. No caller can select tenant, project or storage scope in an authoring request.
7. Application DNS validation is never treated as a replacement for infrastructure egress denial.
8. A failed discovery preserves history but makes the source `stale` and blocks promotion/execution.

## Residual risks

- A public endpoint can behave maliciously while keeping the same advertised contract. Runtime
  approval, least-privilege connections and output handling remain required; schema hashes cannot
  attest implementation behavior.
- Deterministic redaction cannot recognize every secret or personal datum. The durable payload is
  therefore an allowlisted projection, not a copy of the protocol response.
- Azure Storage WORM and CMK strength depend on deployed account policy. Offline tests prove calls
  and contracts, while an environment test must prove the actual immutable/egress configuration.
- A compromised Admin can approve a malicious public endpoint. Separation of decisions, audit and
  least privilege make the action attributable but do not eliminate privileged misuse.

## Required security gates

- SSRF suite: IPv4/IPv6 private classes, metadata, malformed hosts, DNS rebinding and redirects.
- Secret canary suite across document, response, logs, traces, projection, audit and Blob.
- Two-tenant isolation for identical source, Toolbox, connection and tool names.
- Protocol fake proving pagination and the complete absence of `tools/call`.
- Classification conflict matrix and native approval parity.
- Deployed validation of Storage immutability/encryption and network egress policy.
