"use client";

// Sandboxed HTML preview — the reusable rendering primitive shared by the artifact detail
// viewer (SandboxViewer, fetches by id) and the Studio canvas (streams a live `html` string).
//
// SECURITY: the iframe uses `sandbox="allow-scripts"` WITHOUT `allow-same-origin`, giving the
// content an opaque origin. It cannot read the app's cookies, sessionStorage, DOM, or call
// same-origin APIs. Do NOT add `allow-same-origin`: combined with `allow-scripts` it defeats
// the sandbox.
export function LivePreview({ html, title = "artifact-preview" }: { html: string; title?: string }) {
  return (
    <iframe
      title={title}
      srcDoc={html}
      sandbox="allow-scripts"
      style={{ width: "100%", height: "70vh", border: "1px solid var(--border)", borderRadius: 12 }}
    />
  );
}
