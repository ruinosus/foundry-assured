"use client";

// Artifact detail: metadata + governed lifecycle actions (request-approval / approve /
// reject / archive) + the sandboxed HTML preview. Buttons call the proxy; the backend is the
// real enforcement point (require_role), so an unauthorized action surfaces as a load error
// here rather than being hidden client-side.

import { useCallback, useEffect, useState } from "react";
import { authedFetch } from "@/lib/auth/api";
import { SandboxViewer } from "./SandboxViewer";

type Artifact = {
  id: string;
  title: string;
  description: string;
  type: string;
  status: string;
  createdBy: string;
  approvedBy: string | null;
  version: number;
  contentHash: string | null;
  updatedAt: string;
};

const STATUS: Record<string, string> = {
  draft: "neutral",
  pending_approval: "neutral",
  published: "ok",
  rejected: "bad",
  archived: "neutral",
};

export function ArtifactDetail({ id }: { id: string }) {
  const [a, setA] = useState<Artifact | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const r = await authedFetch(`/api/artifacts/${id}`, { cache: "no-store" });
      if (!r.ok) {
        setError(`load failed (${r.status})`);
        return;
      }
      setA(await r.json());
    } catch {
      setError("could not reach the backend");
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  async function act(action: string) {
    setBusy(true);
    setError(null);
    try {
      const r = await authedFetch(`/api/artifacts/${id}/${action}`, { method: "POST" });
      if (!r.ok) {
        setError(`${action} failed (${r.status})`);
        return;
      }
      await load();
    } finally {
      setBusy(false);
    }
  }

  if (error) return <p className="muted">⚠️ {error}</p>;
  if (!a) return <div className="empty">Loading…</div>;

  return (
    <>
      <div>
        <h2 style={{ margin: "0 0 4px" }}>{a.title}</h2>
        <p className="muted" style={{ margin: 0, fontSize: 13 }}>{a.description}</p>
      </div>

      <div style={{ margin: "12px 0", display: "flex", gap: 8, alignItems: "center" }}>
        <span className={`pill ${STATUS[a.status] ?? "neutral"}`}>{a.status}</span>
        <span className="muted">v{a.version}</span>
        {a.contentHash && (
          <span className="muted">· <code>{a.contentHash.slice(0, 12)}…</code></span>
        )}
      </div>

      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        {a.status === "draft" && (
          <button className="btn btn-solid" disabled={busy} onClick={() => act("request-approval")}>
            Request approval
          </button>
        )}
        {a.status === "pending_approval" && (
          <>
            <button className="btn btn-solid" disabled={busy} onClick={() => act("approve")}>
              Approve &amp; publish
            </button>
            <button className="acct-btn" disabled={busy} onClick={() => act("reject")}>
              Reject
            </button>
          </>
        )}
        {(a.status === "published" || a.status === "draft") && (
          <button className="acct-btn" disabled={busy} onClick={() => act("archive")}>
            Archive
          </button>
        )}
      </div>

      <SandboxViewer artifactId={a.id} />
    </>
  );
}
