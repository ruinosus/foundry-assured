"use client";

// Read-only view of real tickets opened by the human-in-the-loop approval flow
// (backend create_ticket tool → data/tickets.jsonl), served via /api/tickets.

import { useEffect, useState } from "react";

type Ticket = {
  id: string;
  summary: string;
  severity: "low" | "medium" | "high";
  status: string;
  created_at: string;
};

const SEV: Record<string, string> = { low: "neutral", medium: "ok", high: "bad" };

export function TicketsView() {
  const [tickets, setTickets] = useState<Ticket[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setError(null);
    try {
      const r = await fetch("/api/tickets", { cache: "no-store" });
      const data = await r.json();
      setTickets(data.tickets ?? []);
      if (data.error) setError(data.error);
    } catch {
      setTickets([]);
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
          <h2 style={{ margin: "0 0 4px" }}>Tickets</h2>
          <p className="muted" style={{ margin: 0, fontSize: 13 }}>
            Real tickets opened by the concierge — the <code>create_ticket</code> tool runs
            only after you approve the escalation in the chat.
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

      {tickets === null ? (
        <div className="empty">Loading…</div>
      ) : tickets.length === 0 ? (
        <div className="table-wrap">
          <div className="empty">
            No tickets yet. In the chat, ask to open one (e.g. “open a ticket to replace my
            mouse”) and <b>approve</b> the escalation card.
          </div>
        </div>
      ) : (
        <div className="table-wrap">
          <table className="evals">
            <thead>
              <tr>
                <th>Ticket</th>
                <th>Summary</th>
                <th>Severity</th>
                <th>Status</th>
                <th>Opened</th>
              </tr>
            </thead>
            <tbody>
              {tickets.map((t) => (
                <tr key={t.id}>
                  <td style={{ fontWeight: 600 }}>{t.id}</td>
                  <td>{t.summary}</td>
                  <td>
                    <span className={`pill ${SEV[t.severity] ?? "neutral"}`}>{t.severity}</span>
                  </td>
                  <td>
                    <span className="pill ok">{t.status}</span>
                  </td>
                  <td style={{ whiteSpace: "nowrap" }}>{new Date(t.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
