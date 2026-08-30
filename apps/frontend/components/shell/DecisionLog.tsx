"use client";

// As decisões desta sessão, no rodapé do dock.
//
// Fica COLAPSADO por padrão e some quando não há nada: um painel vazio com "nenhuma decisão
// ainda" rouba altura do chat, que é o que a pessoa veio usar. Ele aparece quando passa a ter o
// que dizer.
//
// Ver `lib/decision-log.tsx` para por que este log NÃO é a trilha de auditoria.

import { useTranslations } from "next-intl";
import { useDecisionLog, type DecisionOutcome } from "@/lib/decision-log";

/** A cor segue o vocabulário do produto: pass quando a decisão deixou a coisa acontecer, block
 *  quando parou. `edited` é pass — corrigir e aprovar é aprovar. */
const TOM: Record<DecisionOutcome, "pass" | "block"> = {
  accepted: "pass",
  edited: "pass",
  approved: "pass",
  discarded: "block",
  rejected: "block",
};

export function DecisionLog() {
  const t = useTranslations("decisionLog");
  const { decisions } = useDecisionLog();

  if (!decisions.length) return null;

  return (
    <details className="decision-log">
      <summary className="decision-log-head">
        {t("title")} <span className="decision-log-count">{decisions.length}</span>
      </summary>
      <ul className="decision-log-list">
        {decisions.map((d) => (
          <li key={d.id} className="decision-log-item">
            <span className={`decision-log-dot ${TOM[d.outcome]}`} aria-hidden />
            <code className="decision-log-subject">{d.subject}</code>
            <span className="decision-log-outcome">{t(`outcome_${d.outcome}`)}</span>
            <time className="decision-log-at">{d.at}</time>
          </li>
        ))}
      </ul>
    </details>
  );
}
