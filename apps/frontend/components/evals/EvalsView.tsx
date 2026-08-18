"use client";

// Live evaluation runs read from the Foundry project (the canonical store), served
// via /api/evals → backend /eval/foundry. Shows real groundedness/relevance/coherence
// pass counts per run, each linking to its portal report.

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { authedFetch } from "@/lib/auth/api";

const FOUNDRY_PORTAL = "https://ai.azure.com";

type Criterion = { name: string; passed: number; total: number };
type Run = {
  id: string;
  eval_name: string;
  status: string;
  created_at: number; // unix seconds
  report_url: string | null;
  total: number;
  passed: number;
  failed: number;
  criteria: Criterion[];
};

export function EvalsView() {
  const tc = useTranslations("common");
  const t = useTranslations("evals");
  const [runs, setRuns] = useState<Run[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setError(null);
    try {
      const r = await authedFetch("/api/evals", { cache: "no-store" });
      const data = await r.json();
      setRuns(data.runs ?? []);
      // `reason` vem do backend quando a lista está vazia por falha (sem permissão, serviço fora).
      // Sem ele, a tela dizia "nenhuma execução — rode o eval", que é conselho errado quando o
      // problema é permissão: rodar o eval não resolve, e a pessoa tenta várias vezes.
      if (data.error || data.reason) setError(data.error ?? data.reason);
    } catch {
      setRuns([]);
      setError(tc("backendUnreachable"));
    }
  }

  useEffect(() => {
    load();
  }, []);

  const portalLink = runs?.find((r) => r.report_url)?.report_url ?? FOUNDRY_PORTAL;

  return (
    <>
      <div className="between">
        <div>
          <h2>{t("title")}</h2>
          <p className="muted t-sm">
            {t("subtitleLong")}
          </p>
        </div>
        <div className="row-tight">
          <a className="btn" href={portalLink} target="_blank" rel="noreferrer">
            Foundry portal ↗
          </a>
          <button className="btn btn-solid" onClick={load}>
            ↻ Refresh
          </button>
        </div>
      </div>

      {error && (
        <p className="muted">
          ⚠️ {error}
        </p>
      )}

      {runs === null ? (
        <div className="empty">{tc("loading")}</div>
      ) : runs.length === 0 ? (
        <div className="table-wrap">
          <div className="empty">
            No evaluation runs found in the Foundry project yet. Run{" "}
            <code>uv run python -m eval.run_eval --cloud</code> from <code>apps/backend/</code>,
            then refresh — or browse the{" "}
            <a href={FOUNDRY_PORTAL} target="_blank" rel="noreferrer">
              Foundry portal ↗
            </a>
            .
          </div>
        </div>
      ) : (
        <div className="table-wrap">
          <table className="evals">
            <thead>
              <tr>
                <th>When</th>
                <th>Eval</th>
                <th>{t("colStatus")}</th>
                <th>{t("colScores")}</th>
                <th>{t("colReport")}</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => {
                const ok = run.status === "completed" && run.failed === 0;
                return (
                  <tr key={run.id}>
                    <td className="nowrap">
                      {run.created_at ? new Date(run.created_at * 1000).toLocaleString() : "—"}
                    </td>
                    <td>{run.eval_name}</td>
                    <td>
                      <span className={`pill ${ok ? "ok" : run.status === "failed" ? "bad" : "neutral"}`}>
                        {run.status}
                      </span>
                    </td>
                    <td>
                      {run.criteria.length === 0 ? (
                        <span className="muted">—</span>
                      ) : (
                        run.criteria.map((c) => (
                          <span key={c.name} className="score">
                            <span className={`pill ${c.passed === c.total ? "ok" : "bad"}`}>
                              {c.passed}/{c.total}
                            </span>
                            <span className="muted">{c.name}</span>
                          </span>
                        ))
                      )}
                    </td>
                    <td>
                      {run.report_url ? (
                        <a className="link-out" href={run.report_url} target="_blank" rel="noreferrer">
                          Open in Foundry ↗
                        </a>
                      ) : (
                        <span className="muted">—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
