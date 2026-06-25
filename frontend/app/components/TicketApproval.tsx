"use client";

// Human-in-the-loop approval for the backend create_ticket tool.
//
// The backend tool has approval_mode="always_require", so calling it pauses the
// workflow and emits an AG-UI interrupt ({ id, value: function_approval_request }).
// useInterrupt renders this in the chat; resolve() resumes the workflow.
//
// The backend coerces our resolve payload to a function_approval_response when it
// has { approved, id, function_call }, so we echo id + function_call back with the
// developer's decision.

import { useInterrupt } from "@copilotkit/react-core/v2";

const card: React.CSSProperties = {
  border: "1px solid #2563eb33",
  borderLeft: "3px solid #2563eb",
  borderRadius: 8,
  padding: 12,
  margin: "8px 0",
  background: "#eff6ff",
  fontFamily: "system-ui",
  maxWidth: 520,
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
  useInterrupt({
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    render: ({ interrupt, resolve }: any) => {
      const value = interrupt?.value ?? {};
      const fc = value.function_call ?? value.functionCall ?? {};
      let args: Record<string, unknown> = {};
      try {
        args =
          typeof fc.arguments === "string"
            ? JSON.parse(fc.arguments)
            : (fc.arguments ?? fc.args ?? {});
      } catch {
        args = {};
      }

      const respond = (approved: boolean) =>
        resolve({ approved, id: value.id, function_call: fc });

      return (
        <div style={card}>
          <div style={{ fontWeight: 600, marginBottom: 6 }}>
            Open a support ticket?
          </div>
          <div style={{ fontSize: 13, marginBottom: 2 }}>
            <b>Summary:</b> {String(args.summary ?? "(see debug)")}
          </div>
          <div style={{ fontSize: 13, marginBottom: 10 }}>
            <b>Priority:</b> {String(args.priority ?? "medium")}
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button style={btn("#16a34a")} onClick={() => respond(true)}>
              Approve
            </button>
            <button style={btn("#dc2626")} onClick={() => respond(false)}>
              Reject
            </button>
          </div>
          <details style={{ marginTop: 8 }}>
            <summary style={{ fontSize: 11, color: "#94a3b8", cursor: "pointer" }}>
              debug: interrupt
            </summary>
            <pre style={{ fontSize: 11, overflow: "auto", maxHeight: 200 }}>
              {JSON.stringify(interrupt, null, 2)}
            </pre>
          </details>
        </div>
      );
    },
  });

  return null;
}
