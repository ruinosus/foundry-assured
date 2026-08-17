"use client";

// LangGraph's human-in-the-loop approval, on CopilotKit's OWN interrupt hook.
//
// This started as a hand-rolled tap (`agent.subscribe` + parse the CUSTOM event +
// `runAgent({ forwardedProps: { command: { resume } } })`). That is precisely the *legacy*
// branch `useInterrupt` already implements — the adapter even logs
// "forwardedProps.command.resume is deprecated" when it sees it — so the hand-rolled version
// was a reimplementation of a supported contract, and it got the run construction wrong.
//
// The measurement that settled it: driving the SAME endpoint with the SAME resume payload but
// an EMPTY message list, the edit executes and the ticket opens with the approver's
// correction. Driving it through a manual `runAgent`, the client replays the thread's
// messages alongside the resume, the model node runs again, and the middleware interrupts a
// SECOND time — the card reappears with the corrected summary and no ticket is ever created.
// The resume payload was never the bug; the run it rode on was.
//
// Verified against the installed package (`@copilotkit/react-core/dist/*.d.cts`), not a blog:
//   * `useInterrupt` handles BOTH transports — the AG-UI standard outcome and the legacy
//     `on_interrupt` custom event our backend emits today.
//   * for legacy interrupts `resolve(payload)` resumes via `command.resume = payload`, which
//     the adapter turns into `Command(resume=payload)` — the exact call
//     `tests/hitl/edit_roundtrip_test.py` proves round-trips an edit.
//   * `renderInChat: false` returns the element for manual placement, which is how the card
//     keeps its position above the chat instead of inside the transcript.
//
// ADR-020: this is a LangGraph component speaking LangGraph's vocabulary
// (`{ decisions: [{ type, edited_action }] }`). It is deliberately NOT merged with
// TicketApproval — that one serves the Agent Framework domains, whose adapter emits a
// different event (`request_info`) that this hook does not know about. Normalizing the two
// is the abstraction ADR-020 refuses.

import { useInterrupt } from "@copilotkit/react-core/v2";
import { useTranslations } from "next-intl";
import { useState } from "react";

type ActionRequest = { name: string; args: Record<string, unknown> };


/** Pull the middleware's action request out of either transport. */
function readActionRequest(event: { value?: unknown }, interrupt: unknown): ActionRequest | null {
  // Legacy (`on_interrupt`): `value` is a JSON *string*. Standard: the raw payload is kept
  // under `metadata.langgraph.raw` by the adapter's `lg_interrupt_to_agui`.
  const fromStandard = (interrupt as { metadata?: { langgraph?: { raw?: unknown } } } | null)
    ?.metadata?.langgraph?.raw;
  let payload: unknown = fromStandard ?? event?.value;
  if (typeof payload === "string") {
    try {
      payload = JSON.parse(payload);
    } catch {
      return null;
    }
  }
  const req = (payload as { action_requests?: ActionRequest[] } | null)?.action_requests?.[0];
  return req?.name ? req : null;
}

export function GraphApproval({ agentId }: { agentId: string }) {
  return useInterrupt({
    agentId,
    // Manual placement: the card sits above the chat, where the workflow domains put theirs.
    renderInChat: false,
    render: ({ event, interrupt, resolve }) => {
      const req = readActionRequest(event, interrupt);
      if (!req) return <></>;
      return <ApprovalCard req={req} resolve={resolve} />;
    },
  });
}

/** The card is its OWN component, and that is load-bearing rather than cosmetic.
 *
 * `useInterrupt` memoises the element on `[pending, handlerResult, resolve, cancel]` (read in
 * the installed bundle). State held in the hook's *caller* is therefore invisible to that
 * memo: pressing Edit updated `editing`, the memo did not re-run, and the textarea never
 * appeared — the click looked ignored. Owning the state one level down puts it back under
 * ordinary React re-rendering, where the memo is not in the way.
 */
function ApprovalCard({
  req,
  resolve,
}: {
  req: ActionRequest;
  resolve: (payload: unknown) => void | Promise<unknown>;
}) {
  const t = useTranslations("approval");
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);

  const summary = String(req.args?.summary ?? "");

  // LangGraph's own resume vocabulary, straight from `HumanInTheLoopMiddleware`:
  // `{ decisions: [{ type, edited_action? }] }`. `edit` carries the corrected args and is
  // what actually runs, so it is an approval with a diff — never a softer "reject".
  const send = (decision: Record<string, unknown>) => {
    if (busy) return;
    setBusy(true);
    setEditing(false);
    void resolve({ decisions: [decision] });
  };

  return (
        <div className="approval">
          <div className="approval-head">
        <span className="approval-eyebrow">{t("waiting")}</span>
        <h3 className="approval-title">Executar {req.name}?</h3>
      </div>

          {editing ? (
            <div className="approval-edit">
              <label htmlFor="graph-summary" className="approval-eyebrow">
                Resumo
              </label>
              <textarea
                id="graph-summary"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                rows={3}
              />
            </div>
          ) : (
            <dl className="approval-body">
              <dt>{t("summary")}</dt>
              <dd>{summary || JSON.stringify(req.args)}</dd>
            </dl>
          )}

          <div className="approval-actions">
            {editing ? (
              <>
                <button
                  className="btn btn-approve"
                  disabled={busy || !draft.trim()}
                  onClick={() =>
                    // An edit that changes nothing IS an approval — the backend refuses an
                    // empty edit, so send the plain approval rather than a no-op correction.
                    send(
                      draft.trim() === summary
                        ? { type: "approve" }
                        : {
                            type: "edit",
                            edited_action: {
                              name: req.name,
                              args: { ...req.args, summary: draft.trim() },
                            },
                          },
                    )
                  }
                >
                  {t("saveApprove")}
                </button>
                <button className="btn" onClick={() => setEditing(false)}>
                  Cancel
                </button>
              </>
            ) : (
              <>
                <button className="btn btn-approve" disabled={busy} onClick={() => send({ type: "approve" })}>
                  Approve
                </button>
                <button
                  className="btn"
                  disabled={busy}
                  onClick={() => {
                    setDraft(summary);
                    setEditing(true);
                  }}
                >
                  Edit
                </button>
                <button className="btn btn-reject" disabled={busy} onClick={() => send({ type: "reject" })}>
                  Reject
                </button>
              </>
            )}
      </div>
    </div>
  );
}
