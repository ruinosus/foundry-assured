"use client";

// Read-only view of real tickets opened by the human-in-the-loop approval flow
// (backend create_ticket tool → data/tickets.jsonl), served via /api/tickets.

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { authedFetch } from "@/lib/auth/api";

type Ticket = {
  id: string;
  summary: string;
  severity: "low" | "medium" | "high";
  status: string;
  created_at: string;
};

const SEV: Record<string, string> = { low: "neutral", medium: "ok", high: "bad" };

export function TicketsView() {
  const t = useTranslations("tickets");
  const tc = useTranslations("common");
  const [tickets, setTickets] = useState<Ticket[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setError(null);
    try {
      const r = await authedFetch("/api/tickets", { cache: "no-store" });
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
      <div className="between">
        <div>
          <h2>{t("title")}</h2>
          <p className="muted t-sm">
            Real tickets opened by the concierge — the <code>create_ticket</code> tool runs
            only after you approve the escalation in the chat.
          </p>
        </div>
        <button className="btn btn-solid" onClick={load}>
          ↻ Refresh
        </button>
      </div>

      {error && (
        <p className="muted">
          ⚠️ {error}
        </p>
      )}

      {tickets === null ? (
        <div className="empty">{tc("loading")}</div>
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
                <th>{t("colTicket")}</th>
                <th>{t("colSummary")}</th>
                <th>{t("colSeverity")}</th>
                <th>{t("colStatus")}</th>
                <th>{t("colCreated")}</th>
              </tr>
            </thead>
            <tbody>
              {tickets.map((t) => (
                <tr key={t.id}>
                  <td className="strong">{t.id}</td>
                  <td>{t.summary}</td>
                  <td>
                    <span className={`pill ${SEV[t.severity] ?? "neutral"}`}>{t.severity}</span>
                  </td>
                  <td>
                    <span className="pill ok">{t.status}</span>
                  </td>
                  <td className="nowrap">{new Date(t.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
