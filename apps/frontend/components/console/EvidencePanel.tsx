"use client";

// EvidencePanel — hoje só as GARANTIAS de assurance, estáticas.
//
// A evidência de cada resposta (as citações estruturadas) mudou de casa: mora sob a própria
// resposta agora (ver MessageEvidence.tsx / Task 5), lendo o mesmo `useCitationsFor` que este
// painel lia antes. Manter as duas leituras do evento `sources` — uma aqui, outra lá — quebrou:
// o backend passou a mandar `{message_id, citations}` e este painel ainda esperava um array
// solto (`(event.value ?? []).map`), o que estourava TypeError a cada resposta. Em vez de
// consertar uma segunda leitura duplicada do mesmo evento, ela foi removida — `lib/citations.tsx`
// é agora o ÚNICO lugar que interpreta o evento `sources`.
//
// O fallback heurístico que extraía fontes do TEXTO da resposta (regex de caminho de arquivo)
// também saiu: ele existia para cobrir os casos sem citação estruturada, mas com a evidência
// migrando para a mensagem, "sem citação estruturada" agora significa "sem evidência", não
// "hora de adivinhar pelo texto".

import { useTranslations } from "next-intl";

// Mesmo padrão da visão geral: o array guarda a chave, o dicionário guarda a frase.
const GUARANTEES = ["fidelity", "access", "evaluated"] as const;

export function EvidencePanel() {
  const t = useTranslations("console");
  const te = useTranslations("evidence");

  return (
    <aside className="evidence">
      <details className="evidence-section evidence-guar">
        <summary>
          <span aria-hidden>▸</span> {t("guaranteesCount", { count: GUARANTEES.length })}
        </summary>
        <ul className="evidence-guarantees">
          {GUARANTEES.map((g) => (
            <li key={g}>
              <span className="guarantee-icon" aria-hidden>
                ✓
              </span>
              <div>
                <b>{te(`${g}Title`)}</b>
                <p className="muted">{te(g)}</p>
              </div>
            </li>
          ))}
        </ul>
      </details>
    </aside>
  );
}
