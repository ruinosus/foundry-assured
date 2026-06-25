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

import { useAgent } from "@copilotkit/react-core/v2";
import { useEffect, useState } from "react";

type Pending = { id: string; summary: string };

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
          const summary = v.data?.summary ?? v.summary ?? "(no summary)";
          if (id) setPending({ id, summary });
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
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      await (agent as any).runAgent({
        resume: [{ interruptId: id, status: "resolved", payload: approved }],
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={card}>
      <div style={{ fontWeight: 600, marginBottom: 6 }}>Open a support ticket?</div>
      <div style={{ fontSize: 13, marginBottom: 10 }}>
        <b>Summary:</b> {pending.summary}
      </div>
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
