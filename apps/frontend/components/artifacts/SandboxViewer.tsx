"use client";

// Fetches an AI-generated HTML artifact by id and renders it via the shared sandboxed
// LivePreview iframe. The HTML is fetched here with the bearer token (authedFetch) and
// passed via `srcDoc` — the iframe itself never makes an authenticated request. See
// LivePreview.tsx for the sandbox security invariant.

import { useEffect, useState } from "react";
import { authedFetch } from "@/lib/auth/api";
import { LivePreview } from "./LivePreview";

export function SandboxViewer({ artifactId }: { artifactId: string }) {
  const [html, setHtml] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const r = await authedFetch(`/api/artifacts/${artifactId}/content`, {
          cache: "no-store",
        });
        if (!r.ok) throw new Error(`load failed (${r.status})`);
        const text = await r.text();
        if (alive) setHtml(text);
      } catch (e) {
        if (alive) setError((e as Error).message);
      }
    })();
    return () => {
      alive = false;
    };
  }, [artifactId]);

  if (error) return <p className="muted">⚠️ Preview error: {error}</p>;
  if (html === null) return <div className="empty">Loading preview…</div>;

  return <LivePreview html={html} />;
}
