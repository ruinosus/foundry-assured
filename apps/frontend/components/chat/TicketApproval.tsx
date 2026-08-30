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
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { useMyRoles } from "@/lib/auth/roles";
import { useDecisionLog } from "@/lib/decision-log";
import { authConfigured } from "@/lib/auth/msal";

/** Os papéis que podem fazer a ação RODAR. Espelha `ApprovalRequest.required_role` do backend
 *  (hitl/public.py) — e é só isso: um espelho para a tela poder DIZER quem decide. A fronteira
 *  continua sendo o servidor, que recusa `approve` e `edit` de quem não tem o papel. */
const PAPEIS_QUE_APROVAM = ["Approver", "Admin"];

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
  | { kind: "ticket"; id: string; summary: string; reason: string }
  | { kind: "tool"; id: string; toolName: string; args: unknown };


export function TicketApproval({ agentId = "helpdesk" }: { agentId?: string } = {}) {
  const t = useTranslations("approval");
  // The domain is a PROP, not a constant. It was hard-coded to "helpdesk", so on any other
  // domain's page the card subscribed to the wrong agent and never saw the interrupt — the
  // approval simply never appeared. Found by running it, not by reading it.
  const { agent } = useAgent({ agentId });
  const meusPapeis = useMyRoles();
  const { record } = useDecisionLog();
  const [pending, setPending] = useState<Pending | null>(null);
  const [busy, setBusy] = useState(false);
  // O MOTIVO DA RECUSA. Vazio e fechado por padrão: o caminho de aprovar continua em um clique,
  // e o formulário só aparece quando alguém escolhe recusar.
  const [recusando, setRecusando] = useState(false);
  const [motivo, setMotivo] = useState("");
  // The approver's corrected summary. Empty means "not editing" — the card only shows the
  // input once Edit is pressed, so the default path (approve / reject) stays two clicks.
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");

  useEffect(() => {
    if (!agent) return;
    const sub = agent.subscribe({
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
            // O PORQUÊ pode não vir: prompt e código publicam separado (ADR-014), então um
            // backend novo roda com prompt antigo por um tempo. Ausente = a seção não aparece,
            // nunca um placeholder que finge que o agente não justificou.
            const reason = String(data.reason ?? v.reason ?? "");
            setPending({ kind: "ticket", id, summary, reason });
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
  const respond = async (
    payload: boolean | { type: string; args?: Record<string, string>; message?: string },
  ) => {
    if (!agent || busy) return;
    setBusy(true);
    const id = pending.id;
    // O DESFECHO entra no log da sessão antes do resume: se a retomada falhar, a pessoa precisa
    // ver o que ela decidiu — e não decidir de novo achando que não clicou.
    const alvo = pending.kind === "tool" ? pending.toolName : "create_ticket";
    const negou = payload === false || (typeof payload === "object" && payload.type === "reject");
    record(alvo, negou ? "rejected" : "approved");
    setPending(null);
    setEditing(false);
    setRecusando(false);
    setMotivo("");
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

  // QUEM DECIDE, dito na hora de decidir. O card mostrava a ação e os botões, e nada sobre a
  // autoridade de quem estava olhando — então uma pessoa sem o papel clicava em Aprovar e recebia
  // a recusa do servidor como se fosse um erro. Sem auth configurada (dev local) o backend não
  // checa papel nenhum, e a tela diz isso em vez de fingir um papel que não existe.
  const podeAprovar = !authConfigured || (meusPapeis ?? []).some((p) => PAPEIS_QUE_APROVAM.includes(p));
  const meuPapel = (meusPapeis ?? []).filter((p) => PAPEIS_QUE_APROVAM.includes(p)).join(" · ");

  return (
    <div className="approval">
      {pending.kind === "tool" ? (
        <>
          <div className="approval-head">
            <span className="approval-eyebrow">{t("waiting")}</span>
            {/* `approval.run` já existia no dicionário — o título estava em inglês, escrito à
                mão, ao lado da chave que o traduzia. Mesma coisa com Approve/Edit/Reject/Cancel
                abaixo. */}
            <h3 className="approval-title">{t("run", { tool: pending.toolName })}</h3>
          </div>
          <dl className="approval-body">
            <dt>{t("arguments")}</dt>
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
            <span className="approval-eyebrow">{t("waiting")}</span>
            <h3 className="approval-title">{t("openTicket")}</h3>
          </div>
          {editing ? (
            <div className="approval-edit">
              <label htmlFor="ticket-summary" className="approval-eyebrow">
                {t("summary")}
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
              <dt>{t("summary")}</dt>
              <dd>{pending.summary}</dd>
              {/* O PORQUÊ, marcado como o que é: texto do MODELO, não fato verificado.
                  Tipografia deliberadamente diferente do resumo — exibido igual, ele vira uma
                  segunda afirmação com ar de dado, e o aprovador passa a aprovar PELA
                  justificativa em vez de pelo conteúdo, que é o oposto do que este gate faz. */}
              {pending.reason && (
                <>
                  <dt>{t("reason")}</dt>
                  <dd className="approval-reason">
                    <span className="approval-reason-tag">{t("modelSaid")}</span>
                    <span className="muted">{pending.reason}</span>
                  </dd>
                </>
              )}
            </dl>
          )}
        </>
      )}
      <p className={`approval-role ${podeAprovar ? "ok" : "no"}`}>
        {podeAprovar
          ? t("yourRole", { role: meuPapel || t("roleUnchecked") })
          : t("cannotApprove", { roles: PAPEIS_QUE_APROVAM.join(" ou ") })}
      </p>

      {/* RECUSAR EXIGE MOTIVO. Uma recusa em branco obriga quem pediu a adivinhar o que corrigir
          — e o modelo, a tentar de novo igual. O motivo volta na conversa; a trilha registra que
          houve motivo e o tamanho, nunca o texto (ver hitl/public.py). */}
      {recusando && (
        <div className="approval-edit">
          <label htmlFor="reject-reason" className="approval-eyebrow">
            {t("rejectReasonLabel")}
          </label>
          <textarea
            id="reject-reason"
            value={motivo}
            onChange={(e) => setMotivo(e.target.value)}
            rows={2}
            placeholder={t("rejectReasonPlaceholder")}
          />
        </div>
      )}

      <div className="approval-actions">
        {recusando ? (
          <>
            <button
              className="btn btn-reject"
              disabled={busy || !motivo.trim()}
              title={motivo.trim() ? undefined : t("rejectNeedsReason")}
              onClick={() => respond({ type: "reject", message: motivo.trim() })}
            >
              {t("confirmReject")}
            </button>
            <button className="btn" disabled={busy} onClick={() => setRecusando(false)}>
              {t("cancel")}
            </button>
          </>
        ) : editing ? (
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
              {t("saveApprove")}
            </button>
            <button className="btn" disabled={busy} onClick={() => setEditing(false)}>
              {t("cancel")}
            </button>
          </>
        ) : (
          <>
            <button
              className="btn btn-approve"
              disabled={busy || !podeAprovar}
              title={podeAprovar ? undefined : t("cannotApprove", { roles: PAPEIS_QUE_APROVAM.join(" ou ") })}
              onClick={() => respond(true)}
            >
              {t("approve")}
            </button>
            {pending.kind === "ticket" && (
              // Editing is only offered where the backend can apply it. The platform agent's
              // native tool approval is still accept/refuse (ADR-019).
              <button
                className="btn"
                disabled={busy || !podeAprovar}
                title={podeAprovar ? undefined : t("cannotApprove", { roles: PAPEIS_QUE_APROVAM.join(" ou ") })}
                onClick={() => {
                  setDraft(pending.summary);
                  setEditing(true);
                }}
              >
                {t("edit")}
              </button>
            )}
            {/* Recusar não depende de papel: parar uma ação é sempre permitido (hitl/public.py).
                O que mudou é que ela abre o formulário do motivo em vez de responder direto. */}
            <button className="btn btn-reject" disabled={busy} onClick={() => setRecusando(true)}>
              {t("reject")}
            </button>
          </>
        )}
      </div>
    </div>
  );
}
