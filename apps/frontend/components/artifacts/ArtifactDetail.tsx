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
  skill?: string | null;
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
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  // Initial-load failure (no artifact yet) is fatal → full-page error. Once the artifact is
  // loaded, a failed lifecycle action shows an inline banner above the still-rendered content.
  if (!a) return error ? <p className="muted">⚠️ {error}</p> : <div className="empty">Loading…</div>;

  return (
    <div className="studio-canvas">
      <div className="canvas-header">
        <span className="canvas-title-input" style={{ pointerEvents: "none" }}>{a.title}</span>
        <span className="chip-type">{a.type}</span>
        {a.skill && <span className="chip-type">🎨 {a.skill}</span>}
        <span data-testid="status-pill" className={`pill ${STATUS[a.status] ?? "neutral"}`}>{a.status}</span>
        <span className="muted">v{a.version}</span>
        <span style={{ flex: 1 }} />
        {a.status === "draft" && (
          <button data-testid="lifecycle-request-approval" className="btn btn-solid" disabled={busy}
            onClick={() => act("request-approval")}>Request approval</button>
        )}
        {a.status === "pending_approval" && (
          <>
            <button data-testid="lifecycle-approve" className="btn btn-solid" disabled={busy}
              onClick={() => act("approve")}>Approve</button>
            <button data-testid="lifecycle-reject" className="acct-btn" disabled={busy}
              onClick={() => act("reject")}>Reject</button>
          </>
        )}
        {(a.status === "published" || a.status === "draft") && (
          <button data-testid="lifecycle-archive" className="acct-btn" disabled={busy}
            onClick={() => act("archive")}>Archive</button>
        )}
        <a data-testid="detail-open" className="acct-btn" style={{ width: "auto" }}
          href={`/api/artifacts/${a.id}/content`} target="_blank" rel="noreferrer">Open</a>
      </div>
      {error && <p className="muted" style={{ margin: 0 }}>⚠️ {error}</p>}
      <div className="preview-hero">
        <SandboxViewer artifactId={a.id} />
      </div>
      {a.description && <p className="muted" style={{ margin: 0, fontSize: 13 }}>{a.description}</p>}
    </div>
  );
}
