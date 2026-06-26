"use client";

// Read-only view of eval runs recorded by the offline harness
// (backend/eval/run_eval.py -> runs.jsonl), served via /api/evals. The canonical
// store is the Foundry portal Evaluations tab — each cloud run deep-links to it,
// and a fresh deploy (where the local mirror is empty) points there too.

import { useEffect, useState } from "react";
import { authedFetch } from "@/lib/auth/api";

// Canonical home for evaluation runs + the continuous-eval observability dashboard.
const FOUNDRY_PORTAL = "https://ai.azure.com";

type Counts = { passed: number; failed: number; errored?: number };
type Provider = {
  provider: string;
  passed: number;
  total: number;
  failed: number;
  report_url: string | null;
  checks: Record<string, Counts>;
};
type Run = {
  ts: string;
  eval_name: string;
  queries: number;
  cloud: boolean;
  gate_passed: boolean;
  providers: Provider[];
};

function Scores({ provider }: { provider: Provider }) {
  return (
    <div style={{ marginBottom: 6 }}>
      <span className="muted" style={{ marginRight: 8, fontWeight: 600 }}>
        {provider.provider}
      </span>
      {Object.entries(provider.checks).map(([name, c]) => {
        const total = c.passed + c.failed + (c.errored ?? 0);
        const ok = c.failed === 0;
        return (
          <span key={name} className="score">
            <span className={`pill ${ok ? "ok" : "bad"}`}>
              {c.passed}/{total}
            </span>
            <span className="muted">{name}</span>
          </span>
        );
      })}
    </div>
  );
}

export function EvalsView() {
  const [runs, setRuns] = useState<Run[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setError(null);
    try {
      const r = await authedFetch("/api/evals", { cache: "no-store" });
      const data = await r.json();
      setRuns(data.runs ?? []);
      if (data.error) setError(data.error);
    } catch {
      setRuns([]);
      setError("could not reach the backend");
    }
  }

  useEffect(() => {
    load();
  }, []);

  return (
    <>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div>
          <h2 style={{ margin: "0 0 4px" }}>Evaluations</h2>
          <p className="muted" style={{ margin: 0, fontSize: 13 }}>
            Deterministic policy gate plus Foundry hosted judges. Runs execute offline or
            weekly in CI — the canonical scores live in the Foundry portal.
          </p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <a
            className="btn"
            href={runs?.find((r) => r.providers.find((p) => p.report_url))?.providers.find((p) => p.report_url)?.report_url ?? FOUNDRY_PORTAL}
            target="_blank"
            rel="noreferrer"
          >
            Foundry portal ↗
          </a>
          <button className="btn btn-solid" onClick={load}>
            ↻ Refresh
          </button>
        </div>
      </div>

      {error && (
        <p className="muted" style={{ marginTop: 12 }}>
          ⚠️ {error}
        </p>
      )}

      {runs === null ? (
        <div className="empty">Loading…</div>
      ) : runs.length === 0 ? (
        <div className="table-wrap">
          <div className="empty">
            No runs in this local mirror — evals run offline or in CI (the deployed
            container doesn’t run them). The scored runs live in the{" "}
            <a href={FOUNDRY_PORTAL} target="_blank" rel="noreferrer">
              Foundry portal ↗
            </a>
            . To record one here, run <code>uv run python -m eval.run_eval --cloud</code>{" "}
            from <code>apps/backend/</code>.
          </div>
        </div>
      ) : (
        <div className="table-wrap">
          <table className="evals">
            <thead>
              <tr>
                <th>When</th>
                <th>Queries</th>
                <th>Gate</th>
                <th>Scores</th>
                <th>Report</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run, i) => {
                const portal = run.providers.find((p) => p.report_url)?.report_url;
                return (
                  <tr key={`${run.ts}-${i}`}>
                    <td style={{ whiteSpace: "nowrap" }}>
                      {new Date(run.ts).toLocaleString()}
                    </td>
                    <td>{run.queries}</td>
                    <td>
                      <span className={`pill ${run.gate_passed ? "ok" : "bad"}`}>
                        {run.gate_passed ? "passed" : "failed"}
                      </span>
                    </td>
                    <td>
                      {run.providers.map((p) => (
                        <Scores key={p.provider} provider={p} />
                      ))}
                    </td>
                    <td>
                      {portal ? (
                        <a className="link-out" href={portal} target="_blank" rel="noreferrer">
                          Open in Foundry ↗
                        </a>
                      ) : (
                        <span className="muted">local only</span>
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
