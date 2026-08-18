"use client";

// Propor um agente a partir de uma necessidade (ADR-022, Path A).
//
// O QUE ESTA TELA É, e o que ela não é: ela produz um RASCUNHO. Nada aqui publica. O botão final
// não diz "Criar" — diz "Usar este rascunho", e o que ele faz é abrir o wizard de criação com os
// campos preenchidos. Quem publica continua sendo o wizard, com o papel Admin, como sempre foi.
//
// A diferença não é de palavra. Um botão que criasse o agente daqui transformaria a proposta numa
// via de escrita sem revisão — exatamente o que a ADR-022 recusou e o que
// `proposer_read_only_test` verifica do lado do backend.
//
// O QUE FAZ O RASCUNHO SER ÚTIL é o catálogo real ir no contexto: ele escolhe entre as bases que
// existem e aponta os agentes que já cobrem parte da necessidade. Por isso a tela mostra `reuse`
// COM DESTAQUE: a resposta mais valiosa que este painel pode dar é "não crie nada, use aquele".

import { useTranslations } from "next-intl";
import { useState } from "react";
import { authedFetch } from "@/lib/auth/api";
import type { AgentSeed } from "@/components/agents/AgentWizard";

type Draft = {
  name: string;
  display_name: string;
  description: string;
  instructions: string;
  knowledge: string[];
  skills: string[];
  reuse: { name: string; why: string }[];
  rationale: string;
  dropped: string[];
  published: boolean;
  catalog?: Record<string, number>;
};

export function AgentProposer({
  onUse,
  onCancel,
}: {
  onUse: (seed: AgentSeed) => void;
  onCancel: () => void;
}) {
  const t = useTranslations("proposer");
  const tc = useTranslations("common");
  const [need, setNeed] = useState("");
  const [draft, setDraft] = useState<Draft | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const propor = async () => {
    setBusy(true);
    setErro(null);
    setDraft(null);
    try {
      const r = await authedFetch("/api/proposer/draft", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ need }),
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) {
        setErro(body?.error ?? `HTTP ${r.status}`);
        return;
      }
      setDraft(body);
    } catch {
      setErro(tc("backendUnreachable"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="stack-sm">
      <h3 className="section-title">{t("title")}</h3>
      <p className="muted t-sm">{t("help")}</p>

      <textarea
        className="acct-btn"
        rows={3}
        value={need}
        placeholder={t("needPlaceholder")}
        onChange={(e) => setNeed(e.target.value)}
      />
      <div className="row-tight">
        <button
          type="button"
          className="btn btn-solid"
          disabled={busy || !need.trim()}
          onClick={() => void propor()}
        >
          {busy ? t("drafting") : t("draft")}
        </button>
        <button type="button" className="btn" onClick={onCancel}>
          {tc("cancel")}
        </button>
      </div>

      {erro && (
        <div className="notice notice-block">
          <p className="notice-body">{erro}</p>
        </div>
      )}

      {draft && (
        <div className="stack-sm">
          {/* RASCUNHO, dito na tela. Um painel que apresentasse isto como recurso criado seria
              pior que não ter o painel. */}
          <div className="notice notice-wait">
            <p className="notice-body">{t("isDraft")}</p>
          </div>

          {/* O reutilizável vem PRIMEIRO. A pergunta "já existe algo que resolve?" precisa ser
              respondida antes de a pessoa se apegar ao agente novo que acabou de ver nascer. */}
          {draft.reuse.length > 0 && (
            <div className="stack-sm">
              <h4 className="section-title">{t("reuseTitle")}</h4>
              <ul className="plain-list">
                {draft.reuse.map((r) => (
                  <li key={r.name}>
                    <span className="strong t-mono t-sm">{r.name}</span>
                    {r.why && <span className="muted t-sm"> — {r.why}</span>}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="table-wrap">
            <table className="tbl">
              <tbody>
                <tr>
                  <th>{t("fName")}</th>
                  <td className="t-mono t-sm">{draft.name || "—"}</td>
                </tr>
                <tr>
                  <th>{t("fDescription")}</th>
                  <td>{draft.description || "—"}</td>
                </tr>
                <tr>
                  <th>{t("fKnowledge")}</th>
                  <td className="t-sm">{draft.knowledge.join(", ") || "—"}</td>
                </tr>
                <tr>
                  <th>{t("fSkills")}</th>
                  <td className="t-sm">{draft.skills.join(", ") || "—"}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <details>
            <summary className="t-sm">{t("showInstructions")}</summary>
            <pre className="doc-preview">{draft.instructions}</pre>
          </details>

          {draft.rationale && <p className="muted t-sm">{draft.rationale}</p>}

          {/* O que o modelo citou e NÃO existe no projeto. Some do rascunho, mas não em silêncio:
              a pessoa pediu algo que não pôde ser atendido e precisa saber. */}
          {draft.dropped.length > 0 && (
            <p className="t-xs bad-line">
              {t("dropped", { names: draft.dropped.join(", ") })}
            </p>
          )}

          <button
            type="button"
            className="btn btn-solid"
            onClick={() =>
              onUse({
                nome: draft.name,
                descricao: draft.description,
                instrucoes: draft.instructions,
                kb: draft.knowledge[0] ?? "",
              })
            }
          >
            {t("useDraft")}
          </button>
        </div>
      )}
    </section>
  );
}
