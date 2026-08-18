"use client";

// Resultados de um caso de uso — o que ele produziu, e o retorno que isso representa.
//
// ESTA TELA TEM UM RISCO PRÓPRIO, e o desenho existe para desarmá-lo: um painel de ROI é o lugar
// mais fácil de mostrar um número bonito e falso. Conversas, escalações e REFERÊNCIAS CITADAS são
// CONTADAS; as horas assistidas são CALCULADAS. As duas coisas aparecem separadas, com a conta
// visível — quem discordar da premissa vê exatamente onde discordar.
//
// A fórmula não é nossa: é a **Agent Assisted Hours** da Microsoft, e a tela diz isso com o link.
// Antes daqui havia um modelo próprio que se chamava conservador usando 15 min por atendimento
// contra os 6 min que a Microsoft publica com fonte. Premissa de terceiro, citável, vale mais numa
// conversa de negócio do que premissa nossa — e a procedência de cada constante sobe na resposta,
// porque "premissa visível" não é só mostrar o número, é dizer quem o escolheu.
//
// Um ROI cuja premissa está visível é útil. Um que a esconde é propaganda, e a diferença entre os
// dois é só se a premissa aparece na tela.

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";
import { authedFetch } from "@/lib/auth/api";

type Result = {
  conversations: number;
  escalated: number;
  resolved_without_escalation: number;
  resolution_rate: number | null;
  references: number;
  conversations_with_references: number;
  sessions_without_references: number;
  weighted_sessions: number;
  assisted_hours: number;
  assisted_value: number;
  references_partial: boolean;
  input_tokens: number;
  output_tokens: number;
  // `null` = não sabemos o preço deste modelo. Diferente de zero, que seria "não gastou".
  actual_cost: number | null;
  net_saved: number;
  assumption: {
    minutes_per_reference: number;
    resolved_weight: number;
    unresolved_weight: number;
    hourly_cost: number;
    currency: string;
    source: string;
  };
  provenance: {
    formula: string;
    formula_doc: string;
    multiplier_source: string;
    hourly_cost_source: string;
  };
  caveat: string;
  reason: string | null;
};

export function Outcomes({ caseId }: { caseId: string }) {
  const t = useTranslations("outcomes");
  const tc = useTranslations("common");
  const [data, setData] = useState<Result | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [minutos, setMinutos] = useState("6");
  const [custo, setCusto] = useState("90");
  const [busy, setBusy] = useState(false);

  const load = useCallback(
    async (premissa?: { minutes_per_reference: number; hourly_cost: number }) => {
      setBusy(true);
      setErro(null);
      try {
        const r = await authedFetch(`/api/usecases/${encodeURIComponent(caseId)}/outcomes`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(premissa ?? {}),
        });
        const body = await r.json().catch(() => ({}));
        if (!r.ok) {
          setErro(body?.error ?? `HTTP ${r.status}`);
          return;
        }
        setData(body);
        setMinutos(String(body.assumption?.minutes_per_reference ?? 6));
        setCusto(String(body.assumption?.hourly_cost ?? 90));
      } catch {
        setErro(tc("backendUnreachable"));
      } finally {
        setBusy(false);
      }
    },
    [caseId, tc],
  );

  useEffect(() => {
    void load();
  }, [load]);

  const recalcular = () =>
    void load({ minutes_per_reference: Number(minutos), hourly_cost: Number(custo) });

  const moeda = (v: number) =>
    new Intl.NumberFormat(undefined, {
      style: "currency",
      currency: data?.assumption?.currency || "BRL",
    }).format(v);

  return (
    <div className="stack-sm">
      <h3 className="section-title">{t("title")}</h3>

      {erro && (
        <div className="notice notice-block">
          <p className="notice-body">{erro}</p>
        </div>
      )}

      {data && (
        <>
          {/* CONTADO. Fatos sobre o uso — nada aqui depende de premissa. As referências citadas
              entram nesta faixa porque são contadas uma a uma no fim de cada resposta, e são o
              insumo principal da AAH. */}
          <p className="lead-in">{t("measuredLabel")}</p>
          <div className="grid g3">
            <div className="metric">
              <span className="metric-value num">{data.references}</span>
              <span className="metric-label">{t("references")}</span>
            </div>
            <div className="metric">
              <span className="metric-value num">{data.conversations}</span>
              <span className="metric-label">{t("conversations")}</span>
            </div>
            <div className="metric">
              <span className="metric-value num">{data.resolved_without_escalation}</span>
              <span className="metric-label">{t("resolved")}</span>
            </div>
            <div className="metric">
              <span className="metric-value num">
                {data.resolution_rate === null
                  ? "—"
                  : `${Math.round(data.resolution_rate * 100)}%`}
              </span>
              <span className="metric-label">{t("rate")}</span>
            </div>
          </div>

          {/* ESTIMADO. Separado do bloco acima de propósito: misturar os dois faria um cálculo
              parecer uma medida. */}
          <p className="lead-in">{t("estimatedLabel")}</p>
          <div className="notice notice-block">
            <p className="metric-value num">{moeda(data.assisted_value)}</p>
            {/* A CONTA INTEIRA, termo por termo — não só o resultado. */}
            <p className="t-sm muted-line">
              {t("formula", {
                references: data.references,
                weighted: data.weighted_sessions,
                minutes: data.assumption.minutes_per_reference,
                hours: data.assisted_hours,
                cost: moeda(data.assumption.hourly_cost),
              })}
            </p>
            {/* A PROCEDÊNCIA da fórmula, com link. É o que separa "nós achamos" de "a Microsoft
                publica" — e é metade do valor de ter adotado a AAH. */}
            <p className="t-xs muted-line">
              <a href={data.provenance.formula_doc} target="_blank" rel="noreferrer">
                {data.provenance.formula}
              </a>
              {" · "}
              {t("multiplierSource", { source: data.provenance.multiplier_source })}
              {" · "}
              {t("hourlySource", { source: data.provenance.hourly_cost_source })}
            </p>
          </div>

          {/* Referência zerada por FALTA DE DADO não pode parecer resposta sem citação: a
              primeira subestima o valor, a segunda acusa o agente de falha grave. */}
          {data.references_partial && (
            <p className="t-xs bad-line">{t("referencesPartial")}</p>
          )}

          {/* CUSTO REAL — faixa própria, nem com o contado nem com o estimado. Os tokens são
              medidos; o preço por token é tabela editável. Misturá-lo com a economia estimada
              faria a conta parecer toda medida, e misturá-lo com o contado esconderia que o
              preço é premissa. */}
          <p className="lead-in">{t("costLabelBand")}</p>
          <div className="grid g3">
            <div className="metric">
              {/* Preço desconhecido não vira R$ 0,00: zero e "não sei" levam a conclusões
                  opostas, e o motivo aparece na ressalva abaixo. */}
              <span className="metric-value num">
                {data.actual_cost === null ? "—" : moeda(data.actual_cost)}
              </span>
              <span className="metric-label">{t("actualCost")}</span>
            </div>
            <div className="metric">
              <span className="metric-value num">
                {((data.input_tokens + data.output_tokens) / 1000).toFixed(1)}K
              </span>
              <span className="metric-label">{t("tokens")}</span>
            </div>
            <div className="metric">
              {/* Líquido negativo é INFORMAÇÃO, não erro: este caso gastou mais em modelo do que
                  economizou sob a premissa. Marcado, não escondido. */}
              <span className={`metric-value num${data.net_saved < 0 ? " bad-line" : ""}`}>
                {moeda(data.net_saved)}
              </span>
              <span className="metric-label">{t("netSaved")}</span>
            </div>
          </div>

          <div className="row-tight">
            <label className="t-xs muted-line">{t("minutesLabel")}</label>
            <input
              className="acct-btn"
              type="number"
              min={1}
              max={480}
              value={minutos}
              onChange={(e) => setMinutos(e.target.value)}
            />
            <label className="t-xs muted-line">{t("costLabel")}</label>
            <input
              className="acct-btn"
              type="number"
              min={1}
              value={custo}
              onChange={(e) => setCusto(e.target.value)}
            />
            <button type="button" className="btn" disabled={busy} onClick={recalcular}>
              {busy ? t("calculating") : t("recalculate")}
            </button>
          </div>

          {/* A ressalva não fica em letra miúda escondida: é parte do número. */}
          <p className="muted t-xs">{data.caveat}</p>
          {data.reason && <p className="t-xs bad-line">{data.reason}</p>}
          {data.assumption.source === "default" && (
            <p className="t-xs muted-line">{t("defaultAssumption")}</p>
          )}
        </>
      )}
    </div>
  );
}
