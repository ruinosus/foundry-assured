"use client";

// Live workflow steps panel. Subscribes to the agent's event stream
// (onActivitySnapshotEvent) for per-executor progress, and onRunFinalized to
// flip any still-running step to done — which fixes the terminal "resolve" step
// staying blue (its completion is emitted as the streamed answer, not a clean
// completed activity).
//
// useAgent lives in @copilotkit/react-core/v2/headless; the agent is an
// @ag-ui/client AbstractAgent whose subscribe() exposes these hooks.

// Import from /v2 (same entry as CopilotKitProvider) so the CopilotKit context
// is shared — importing useAgent from /v2/headless uses a separate context copy
// and throws "useCopilotKit must be used within CopilotKitProvider".
import { useAgent } from "@copilotkit/react-core/v2";
import { useEffect, useState } from "react";

const STEPS = [
  { id: "triage", label: "Triage", desc: "Classify intent & urgency" },
  { id: "retrieve", label: "Retrieve", desc: "Search the runbook knowledge base" },
  { id: "resolve", label: "Resolve", desc: "Write the grounded, cited answer" },
] as const;

type StepState = "idle" | "active" | "done" | "pending";

const DOT: Record<StepState, string> = {
  idle: "#cbd5e1",
  pending: "#cbd5e1",
  active: "#2563eb",
  done: "#16a34a",
};

export function WorkflowSteps() {
  const { agent } = useAgent({ agentId: "helpdesk" });
  const [status, setStatus] = useState<Record<string, string>>({});
  const [running, setRunning] = useState(false);

  useEffect(() => {
    if (!agent) return;
    const sub = agent.subscribe({
      // TEMP debug: log every AG-UI event so we can see how the approval
      // interrupt / WorkflowInterruptEvent arrives. Remove once HITL renders.
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      onEvent: ({ event }: any) => {
        // eslint-disable-next-line no-console
        console.log("[ag-ui]", event?.type, event);
      },
      onRunInitialized: () => {
        setStatus({});
        setRunning(true);
      },
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      onActivitySnapshotEvent: ({ event }: any) => {
        const content = event?.content ?? event?.payload?.content;
        const id: string | undefined = content?.executor_id;
        if (id) setStatus((prev) => ({ ...prev, [id]: content.status }));
      },
      onRunFinalized: () => {
        setRunning(false);
        // The run finished successfully, so every step ran — mark them all done
        // (the terminal step never emits a clean "completed" activity).
        setStatus(() => Object.fromEntries(STEPS.map((s) => [s.id, "completed"])));
      },
      onRunFailed: () => setRunning(false),
    });
    return () => sub.unsubscribe();
  }, [agent]);

  const hasAny = running || Object.keys(status).length > 0;

  function stateFor(id: string): StepState {
    const s = status[id];
    if (s === "completed") return "done";
    if (s === "in_progress") return "active";
    return running ? "pending" : "idle";
  }

  return (
    <section
      style={{
        borderBottom: "1px solid #e5e7eb",
        padding: "12px 24px",
        fontFamily: "system-ui",
      }}
    >
      <div style={{ fontSize: 12, color: "#64748b", marginBottom: 8 }}>
        Workflow {running ? "· running…" : hasAny ? "· done" : "· idle"}
      </div>
      <ol
        style={{
          display: "flex",
          gap: 8,
          listStyle: "none",
          margin: 0,
          padding: 0,
          flexWrap: "wrap",
        }}
      >
        {STEPS.map((s) => {
          const st = stateFor(s.id);
          return (
            <li
              key={s.id}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                padding: "6px 10px",
                border: `1px solid ${st === "active" ? DOT.active : "#e5e7eb"}`,
                borderRadius: 8,
                background:
                  st === "active" ? "#eff6ff" : st === "done" ? "#f0fdf4" : "transparent",
                opacity: st === "pending" || st === "idle" ? 0.6 : 1,
              }}
            >
              <span aria-hidden style={{ fontSize: 13, color: DOT[st] }}>
                {st === "done" ? "✓" : "●"}
              </span>
              <span style={{ fontSize: 13, fontWeight: 600 }}>{s.label}</span>
              <span style={{ fontSize: 12, color: "#94a3b8" }}>{s.desc}</span>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
