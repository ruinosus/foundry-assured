"use client";

// HTML Artifacts workspace: generate an AI HTML report/presentation/walkthrough via the
// governed /artifacts/html/generate endpoint, then list what's been created. Approval,
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
  const [busy, setBusy] = useState(false);
  const [title, setTitle] = useState("");
  const [prompt, setPrompt] = useState("");
  const [type, setType] = useState("report");

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

  async function generate() {
    setBusy(true);
    setError(null);
    try {
      const r = await authedFetch("/api/artifacts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, prompt, type }),
      });
      if (!r.ok) throw new Error(`generate failed (${r.status})`);
      setTitle("");
      setPrompt("");
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

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
        <button className="btn btn-solid" onClick={load}>
          ↻ Refresh
        </button>
      </div>

      <section className="card" style={{ marginTop: 16 }}>
        <h3 style={{ marginTop: 0 }}>Generate HTML artifact</h3>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <label className="muted" style={{ fontSize: 12 }}>Title</label>
          <input
            className="acct-btn"
            style={{ cursor: "text" }}
            placeholder="Q3 status report"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
          <label className="muted" style={{ fontSize: 12 }}>Type</label>
          <select className="acct-btn" value={type} onChange={(e) => setType(e.target.value)}>
            <option value="report">Report</option>
            <option value="presentation">Presentation</option>
            <option value="walkthrough">Walkthrough</option>
          </select>
          <label className="muted" style={{ fontSize: 12 }}>Prompt</label>
          <textarea
            className="acct-btn"
            style={{ cursor: "text", resize: "vertical" }}
            placeholder="Describe what to generate…"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            rows={3}
          />
        </div>
        <div style={{ marginTop: 12 }}>
          <button className="btn btn-solid" disabled={busy || !title || !prompt} onClick={generate}>
            {busy ? "Generating…" : "Generate"}
          </button>
        </div>
      </section>

      {error && (
        <p className="muted" style={{ marginTop: 12 }}>
          ⚠️ {error}
        </p>
      )}

      {items === null ? (
        <div className="empty">Loading…</div>
      ) : items.length === 0 ? (
        <div className="table-wrap">
          <div className="empty">No artifacts yet. Generate one above.</div>
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
