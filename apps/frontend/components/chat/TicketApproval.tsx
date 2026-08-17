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
// LangGraph domains are NOT handled here. They go through `GraphApproval`, which uses
// CopilotKit's own `useInterrupt` — the hook already implements this tap, and gets the resume
// run right (it replays the interrupted `runId` instead of the thread's messages, which is
// what made a hand-rolled resume interrupt a second time instead of executing). This file
// stays for the Agent Framework domains, whose adapter emits `request_info`, which that hook
// does not know about. ADR-020: two runtimes, two idioms, no normalizing layer.
type Pending =
  | { kind: "ticket"; id: string; summary: string }
  | { kind: "tool"; id: string; toolName: string; args: unknown };


export function TicketApproval({ agentId = "helpdesk" }: { agentId?: string } = {}) {
  // The domain is a PROP, not a constant. It was hard-coded to "helpdesk", so on any other
  // domain's page the card subscribed to the wrong agent and never saw the interrupt — the
  // approval simply never appeared. Found by running it, not by reading it.
  const { agent } = useAgent({ agentId });
  const [pending, setPending] = useState<Pending | null>(null);
  const [busy, setBusy] = useState(false);
  // The approver's corrected summary. Empty means "not editing" — the card only shows the
  // input once Edit is pressed, so the default path (approve / reject) stays two clicks.
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");

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

  // The payload is either the legacy boolean or a decision object. The backend accepts both
  // and treats anything unrecognized as a REJECT, so a malformed payload can never be the
  // reason a ticket opens (ADR-019).
  const respond = async (payload: boolean | { type: string; args?: Record<string, string> }) => {
    if (!agent || busy) return;
    setBusy(true);
    const id = pending.id;
    setPending(null);
    setEditing(false);
    try {
      // Send the AG-UI array form (the CopilotKit runtime validates this); the
      // runtime route rewrites it to the backend's dict form before forwarding.
      await agent.runAgent({
        resume: [{ interruptId: id, status: "resolved", payload }],
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="approval">
      {pending.kind === "tool" ? (
        <>
          <div className="approval-head">
            <span className="approval-eyebrow">Aguardando aprovação</span>
            <h3 className="approval-title">
              Executar <code>{pending.toolName}</code>?
            </h3>
          </div>
          <dl className="approval-body">
            <dt>Argumentos</dt>
            <dd>
              <code>
              {typeof pending.args === "string"
                ? pending.args
                : JSON.stringify(pending.args ?? {}, null, 2)}
              </code>
            </dd>
          </dl>
        </>
      ) : (
        <>
          <div className="approval-head">
            <span className="approval-eyebrow">Aguardando aprovação</span>
            <h3 className="approval-title">Abrir chamado?</h3>
          </div>
          {editing ? (
            <div className="approval-edit">
              <label htmlFor="ticket-summary" className="approval-eyebrow">
                Resumo
              </label>
              <textarea
                id="ticket-summary"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                rows={3}
              />
            </div>
          ) : (
            <dl className="approval-body">
              <dt>Resumo</dt>
              <dd>{pending.summary}</dd>
            </dl>
          )}
        </>
      )}
      <div className="approval-actions">
        {editing ? (
          <>
            {/* An edit that changes nothing is an approval — the backend refuses an empty
                edit, so send the plain approval rather than a no-op correction. */}
            <button
              className="btn btn-approve"
              disabled={busy || !draft.trim()}
              onClick={() =>
                respond(
                  pending.kind === "ticket" && draft.trim() === pending.summary
                    ? { type: "approve" }
                    : { type: "edit", args: { summary: draft.trim() } },
                )
              }
            >
              Salvar e aprovar
            </button>
            <button className="btn" disabled={busy} onClick={() => setEditing(false)}>
              Cancel
            </button>
          </>
        ) : (
          <>
            <button className="btn btn-approve" disabled={busy} onClick={() => respond(true)}>
              Approve
            </button>
            {pending.kind === "ticket" && (
              // Editing is only offered where the backend can apply it. The platform agent's
              // native tool approval is still accept/refuse (ADR-019).
              <button
                className="btn"
                disabled={busy}
                onClick={() => {
                  setDraft(pending.summary);
                  setEditing(true);
                }}
              >
                Edit
              </button>
            )}
            <button className="btn btn-reject" disabled={busy} onClick={() => respond(false)}>
              Reject
            </button>
          </>
        )}
      </div>
    </div>
  );
}
