"use client";

// HTML Artifacts workspace: list what's been created; new artifacts are authored in the
// Artifacts Studio (/artifacts/new — a conversational canvas with a live preview). Approval,
// publishing, and preview happen on the detail page (/artifacts/[id]).

import { useEffect, useState } from "react";
import Link from "next/link";
import { authedFetch } from "@/lib/auth/api";

type Artifact = {
  id: string;
  title: string;
  type: string;
  status: string;
  createdBy: string;
  updatedAt: string;
};

const STATUS: Record<string, string> = {
  draft: "neutral",
  pending_approval: "neutral",
  published: "ok",
  rejected: "bad",
  archived: "neutral",
};

export function ArtifactsView() {
  const [items, setItems] = useState<Artifact[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setError(null);
    try {
      const r = await authedFetch("/api/artifacts", { cache: "no-store" });
      const data = await r.json();
      setItems(data.artifacts ?? []);
      if (data.error) setError(data.error);
    } catch {
      setItems([]);
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
          <h2 style={{ margin: "0 0 4px" }}>Artifacts</h2>
          <p className="muted" style={{ margin: 0, fontSize: 13 }}>
            AI-generated HTML reports, presentations, and walkthroughs — sandboxed, versioned,
            and gated behind an approve-to-publish lifecycle.
          </p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <Link className="btn btn-solid" href="/artifacts/new">
            ＋ New artifact
          </Link>
          <button className="acct-btn" onClick={load}>
            ↻ Refresh
          </button>
        </div>
      </div>

      {error && (
        <p className="muted" style={{ marginTop: 12 }}>
          ⚠️ {error}
        </p>
      )}

      {items === null ? (
        <div className="empty">Loading…</div>
      ) : items.length === 0 ? (
        <div className="table-wrap">
          <div className="empty">No artifacts yet. Create one in the Studio above.</div>
        </div>
      ) : (
        <div className="table-wrap">
          <table className="evals">
            <thead>
              <tr>
                <th>Title</th>
                <th>Type</th>
                <th>Status</th>
                <th>Updated</th>
              </tr>
            </thead>
            <tbody>
              {items.map((a) => (
                <tr key={a.id}>
                  <td style={{ fontWeight: 600 }}>
                    <Link className="link-out" href={`/artifacts/${a.id}`}>{a.title}</Link>
                  </td>
                  <td>{a.type}</td>
                  <td>
                    <span className={`pill ${STATUS[a.status] ?? "neutral"}`}>{a.status}</span>
                  </td>
                  <td style={{ whiteSpace: "nowrap" }}>{new Date(a.updatedAt).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
