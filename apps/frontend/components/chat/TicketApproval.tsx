"use client";

// Human-in-the-loop ticket approval.
//
// CopilotKit's useInterrupt doesn't pick up the agent-framework workflow
// interrupt (the adapter emits RUN_FINISHED with a singular `interrupt` field +
// a `request_info` CUSTOM event, which v2's interrupt detection doesn't match).
// So we tap the agent's event stream directly (the same subscribe the steps use)
// and drive the approval ourselves:
//   - catch the `request_info` CUSTOM event -> { request_id, data: { summary } }
//   - on approve/reject, resume the paused workflow with
//     agent.runAgent({ resume: [{ interruptId, status: "resolved", payload: bool }] })
//
// Verified against the captured AG-UI event stream + @ag-ui/client
// (AbstractAgent.runAgent / ResumeEntry).
//
// The same tap also (best-effort) handles the platform agent's native MCP
// write-tool approval (agent-framework ToolApprovalRequestContent). The exact
// AG-UI shape of that native tool-approval is pending live verification (see the
// #3199 note on the discriminator below); we resume it via the identical
// runAgent({ resume }) mechanism.

import { useAgent } from "@copilotkit/react-core/v2";
import { useEffect, useState } from "react";

// Two shapes of interrupt arrive over the SAME request_info/CUSTOM-event tap:
//   - "ticket": the helpdesk workflow's create_ticket HITL -> { data: { summary } }
//   - "tool":   the platform agent's native MCP write-tool approval
//               (agent-framework ToolApprovalRequestContent) -> tool name + args
type Pending =
  | { kind: "ticket"; id: string; summary: string }
  | { kind: "tool"; id: string; toolName: string; args: unknown };

const card: React.CSSProperties = {
  border: "1px solid #2563eb33",
  borderLeft: "3px solid #2563eb",
  borderRadius: 8,
  padding: 12,
  margin: "0 24px 8px",
  background: "#eff6ff",
  fontFamily: "system-ui",
};
const btn = (bg: string): React.CSSProperties => ({
  padding: "6px 14px",
  borderRadius: 6,
  border: "none",
  background: bg,
  color: "white",
  cursor: "pointer",
  fontSize: 13,
  fontWeight: 600,
});

export function TicketApproval() {
  const { agent } = useAgent({ agentId: "helpdesk" });
  const [pending, setPending] = useState<Pending | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!agent) return;
    const sub = agent.subscribe({
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      onEvent: ({ event }: any) => {
        if (event?.type === "CUSTOM" && event?.name === "request_info") {
          const v = event.value ?? {};
          const id = v.request_id ?? v.id;
          if (!id) return;
          const data = v.data ?? v;

          // Discriminate on payload shape: a ToolApprovalRequestContent carries a
          // tool name (+ call arguments) rather than the create_ticket `summary`.
          // NOTE: ToolApprovalRequestContent event shape is unverified vs #3199 —
          // confirm in the E2E and adjust the discriminator/payload mapping if it
          // surfaces differently.
          const toolName =
            data.tool_name ?? data.name ?? data.function_name ?? data.toolName;
          const args =
            data.arguments ?? data.args ?? data.tool_arguments ?? data.parameters;

          if (toolName) {
            setPending({ kind: "tool", id, toolName, args });
          } else {
            const summary = data.summary ?? v.summary ?? "(no summary)";
            setPending({ kind: "ticket", id, summary });
          }
        }
      },
    });
    return () => sub.unsubscribe();
  }, [agent]);

  if (!pending) return null;

  const respond = async (approved: boolean) => {
    if (!agent || busy) return;
    setBusy(true);
    const id = pending.id;
    setPending(null);
    try {
      // Send the AG-UI array form (the CopilotKit runtime validates this); the
      // runtime route rewrites it to the backend's dict form before forwarding.
      await agent.runAgent({
        resume: [{ interruptId: id, status: "resolved", payload: approved }],
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={card}>
      {pending.kind === "tool" ? (
        <>
          <div style={{ fontWeight: 600, marginBottom: 6 }}>
            Run write tool <code>{pending.toolName}</code>?
          </div>
          <div style={{ fontSize: 13, marginBottom: 10 }}>
            <b>Arguments:</b>{" "}
            <code style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
              {typeof pending.args === "string"
                ? pending.args
                : JSON.stringify(pending.args ?? {}, null, 2)}
            </code>
          </div>
        </>
      ) : (
        <>
          <div style={{ fontWeight: 600, marginBottom: 6 }}>Open a support ticket?</div>
          <div style={{ fontSize: 13, marginBottom: 10 }}>
            <b>Summary:</b> {pending.summary}
          </div>
        </>
      )}
      <div style={{ display: "flex", gap: 8 }}>
        <button style={btn("#16a34a")} disabled={busy} onClick={() => respond(true)}>
          Approve
        </button>
        <button style={btn("#dc2626")} disabled={busy} onClick={() => respond(false)}>
          Reject
        </button>
      </div>
    </div>
  );
}
