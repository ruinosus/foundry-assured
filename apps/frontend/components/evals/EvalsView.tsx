"use client";

// Read-only view of eval runs recorded by the offline harness
// (backend/eval/run_eval.py -> runs.jsonl), served via /api/evals. Each run links
// to its Foundry portal report when the cloud judges ran.

import { useEffect, useState } from "react";

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
      const r = await fetch("/api/evals", { cache: "no-store" });
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
            Offline harness runs — deterministic policy gate plus Foundry hosted judges.
            Each cloud run links to its report in the Foundry portal.
          </p>
        </div>
        <button className="btn btn-solid" onClick={load}>
          ↻ Refresh
        </button>
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
            No runs yet. From <code>backend/</code>, run{" "}
            <code>uv run python -m eval.run_eval --cloud</code> to record one.
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
