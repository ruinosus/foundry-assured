"use client";

// Resultados de um caso de uso — o que ele produziu, e o retorno que isso representa.
//
// ESTA TELA TEM UM RISCO PRÓPRIO, e o desenho existe para desarmá-lo: um painel de ROI é o lugar
// mais fácil de mostrar um número bonito e falso. Conversas e escalações são CONTADAS; a economia
// é CALCULADA sobre uma premissa que a empresa informa. As duas coisas aparecem separadas, com a
// conta visível — quem discordar da premissa vê exatamente onde discordar.
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
  estimated_minutes_saved: number;
  estimated_cost_saved: number;
  input_tokens: number;
  output_tokens: number;
  actual_cost: number;
  net_saved: number;
  assumption: { minutes_per_case: number; hourly_cost: number; currency: string; source: string };
  caveat: string;
  reason: string | null;
};

export function Outcomes({ caseId }: { caseId: string }) {
  const t = useTranslations("outcomes");
  const tc = useTranslations("common");
  const [data, setData] = useState<Result | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [minutos, setMinutos] = useState("15");
  const [custo, setCusto] = useState("90");
  const [busy, setBusy] = useState(false);

  const load = useCallback(
    async (premissa?: { minutes_per_case: number; hourly_cost: number }) => {
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
        setMinutos(String(body.assumption?.minutes_per_case ?? 15));
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
    void load({ minutes_per_case: Number(minutos), hourly_cost: Number(custo) });

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
          {/* CONTADO. Estes três vieram do serviço — são fatos sobre o uso. */}
          <p className="lead-in">{t("measuredLabel")}</p>
          <div className="grid g3">
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
          <div className="notice">
            <p className="metric-value num">{moeda(data.estimated_cost_saved)}</p>
            {/* A CONTA INTEIRA, não só o resultado. */}
            <p className="t-sm muted-line">
              {t("formula", {
                cases: data.resolved_without_escalation,
                minutes: data.assumption.minutes_per_case,
                cost: moeda(data.assumption.hourly_cost),
              })}
            </p>
          </div>

          {/* CUSTO REAL — faixa própria, nem com o contado nem com o estimado. Os tokens são
              medidos; o preço por token é tabela editável. Misturá-lo com a economia estimada
              faria a conta parecer toda medida, e misturá-lo com o contado esconderia que o
              preço é premissa. */}
          <p className="lead-in">{t("costLabelBand")}</p>
          <div className="grid g3">
            <div className="metric">
              <span className="metric-value num">{moeda(data.actual_cost)}</span>
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
