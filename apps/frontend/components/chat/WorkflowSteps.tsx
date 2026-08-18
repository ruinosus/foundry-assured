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
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

// O `id` é contrato: é o nome do passo no snapshot de estado que o workflow emite. Rótulo e
// descrição são texto, e por isso vivem no dicionário sob a mesma chave.
const STEPS = ["triage", "retrieve", "resolve"] as const;

type StepState = "idle" | "active" | "done" | "pending";

// Estado do passo é semântica, não enfeite: "rodando agora" usa o accent (a atenção está
// ali) e "concluído" usa --pass (o mesmo verde que diz "o gate aprovou" em toda a interface).
// Antes eram hex cravados — #cbd5e1/#2563eb/#16a34a — que no tema escuro sumiam ou brigavam.

export function WorkflowSteps() {
  const t = useTranslations("workflow");
  const { agent } = useAgent({ agentId: "helpdesk" });
  const [status, setStatus] = useState<Record<string, string>>({});
  const [running, setRunning] = useState(false);

  useEffect(() => {
    if (!agent) return;
    const sub = agent.subscribe({
      onRunInitialized: () => {
        setStatus({});
        setRunning(true);
      },
      onActivitySnapshotEvent: ({ event }: any) => {
        const content = event?.content ?? event?.payload?.content;
        const id: string | undefined = content?.executor_id;
        if (id) setStatus((prev) => ({ ...prev, [id]: content.status }));
      },
      onRunFinalized: () => {
        setRunning(false);
        // The run finished successfully, so every step ran — mark them all done
        // (the terminal step never emits a clean "completed" activity).
        setStatus(() => Object.fromEntries(STEPS.map((id) => [id, "completed"])));
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

  // SÓ DURANTE A EXECUÇÃO, e por pouco tempo depois. Antes era um bloco fixo acima do chat,
  // ocupando altura permanente para dizer "idle" — informação de zero valor que empurrava a
  // conversa para baixo em toda visita. Agora aparece quando roda e sai quando termina.
  if (!hasAny) return null;

  return (
    <div className={`steps-strip${running ? " running" : ""}`} aria-live="polite">
      <span className="steps-label">{running ? t("running") : t("done")}</span>
      <ol className="steps-flow">
        {STEPS.map((id, i) => {
          const st = stateFor(id);
          return (
            <li key={id} className={`step-${st}`}>
              {i > 0 && <span className="step-arrow" aria-hidden>→</span>}
              <span className="step-pip" aria-hidden />
              <span className="step-name">{t(`${id}Label`)}</span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
