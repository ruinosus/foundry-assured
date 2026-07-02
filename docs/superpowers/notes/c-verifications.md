# Sub-project C — SDK / bug verifications (plan Task 0)

Verified against the installed versions on `develop` (`agent_framework` 1.9.0, `azure-ai-projects` 2.x). These resolve the three unknowns the C plan gated on.

| Unknown | Finding | Impact on the plan |
|---|---|---|
| **`MCPSpecificApproval` shape** (per-tool `approval_mode` dict) | `agent_framework._mcp.MCPSpecificApproval` is a TypedDict with keys **`always_require_approval`** and **`never_require_approval`**, each `Collection[str] \| None`. (NOT `always_require`/`never_require`.) `MCPStreamableHTTPTool.approval_mode: Literal['always_require','never_require'] \| MCPSpecificApproval \| None`. | **Task 4 uses `{"always_require_approval": [<writes>], "never_require_approval": [<reads>]}`** — corrected from the plan's earlier `always_require`/`never_require` guess. |
| **`azure-ai-projects` get-connection-with-credentials** | `ConnectionsOperations.get(name, *, include_credentials: bool = False) -> Connection` **exists** (also `get_default(connection_type, include_credentials=...)`). | **Task 5 internal SDK-broker is FEASIBLE** (not deferred): `client.connections.get(conn.foundry_connection_id, include_credentials=True)`. Confirm the credential field on the returned `Connection` model when implementing (e.g. `.credentials` / api-key field). |
| **Bug #3199** (AG-UI `always_require` not executing) | `agent_framework` 1.9.0; fix status **not determinable from the version alone**. The `approval_mode` dict construction is unit-testable; whether it actually fires over the AG-UI adapter is only testable live. | **Write-approval over AG-UI stays infra-gated** (Task 8 E2E is the real test). Task 7 extends `TicketApproval.tsx` for the `request_info`/`ToolApprovalRequestContent` event; if the live test shows it surfaces differently, scope the new event branch then. |

**Net:** all three credential mechanisms (OBO, hosted Foundry-connection, internal SDK-broker) are implementable now; only the live AG-UI write-approval firing (#3199) remains a runtime verification.
