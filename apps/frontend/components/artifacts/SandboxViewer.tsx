"use client";

// Renders an AI-generated HTML artifact in an isolated sandbox.
//
// SECURITY: the iframe uses `sandbox="allow-scripts"` WITHOUT `allow-same-origin`,
// giving the content an opaque origin. It cannot read the app's cookies,
// sessionStorage, DOM, or call same-origin APIs. The HTML is fetched here with
// the bearer token (authedFetch) and passed via `srcDoc` — the iframe itself
// never makes an authenticated request. Do NOT add `allow-same-origin`:
// combined with `allow-scripts` it defeats the sandbox.

import { useEffect, useState } from "react";
import { authedFetch } from "@/lib/auth/api";

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

  return (
    <iframe
      title="artifact-preview"
      srcDoc={html}
      sandbox="allow-scripts"
      style={{ width: "100%", height: "70vh", border: "1px solid var(--border)", borderRadius: 12 }}
    />
  );
}
