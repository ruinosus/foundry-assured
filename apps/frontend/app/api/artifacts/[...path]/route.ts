// Catch-all proxy for per-artifact routes: GET /{id}, GET /{id}/content, and the lifecycle
// POSTs (/{id}/request-approval, /approve, /reject, /archive). Forwards the caller's Entra
// bearer token; the backend's require_role gate is the real enforcement point.
//
// Unlike every other proxy in this app, this one passes through the upstream Content-Type
// verbatim instead of forcing application/json — /{id}/content returns text/html (with a
// `Content-Security-Policy: sandbox` header from the backend), and that must reach the
// browser unchanged so SandboxViewer can inject it as srcDoc.
import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";
const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

async function forward(req: NextRequest, path: string[], method: "GET" | "POST") {
  try {
    const auth = req.headers.get("authorization");
    const url = `${BACKEND}/artifacts/html/${path.join("/")}`;
    const r = await fetch(url, {
      method,
      cache: "no-store",
      headers: auth ? { Authorization: auth } : undefined,
      body: method === "POST" ? await req.text() : undefined,
    });
    const ct = r.headers.get("content-type") ?? "application/json";
    const buf = await r.arrayBuffer();
    // Carry the backend's defense-in-depth headers for /content (sandbox CSP + nosniff) so a
    // direct navigation to the proxied HTML is still browser-sandboxed. Explicitly forwarded
    // (never spread all of r.headers — that would leak hop-by-hop headers like
    // content-encoding/content-length that no longer match the re-emitted body).
    const headers: Record<string, string> = { "Content-Type": ct };
    const csp = r.headers.get("content-security-policy");
    if (csp) headers["Content-Security-Policy"] = csp;
    const xcto = r.headers.get("x-content-type-options");
    if (xcto) headers["X-Content-Type-Options"] = xcto;
    return new NextResponse(buf, { status: r.status, headers });
  } catch {
    return NextResponse.json({ error: "backend unreachable" }, { status: 502 });
  }
}

type Ctx = { params: Promise<{ path: string[] }> };

export async function GET(req: NextRequest, ctx: Ctx) {
  const { path } = await ctx.params;
  return forward(req, path, "GET");
}

export async function POST(req: NextRequest, ctx: Ctx) {
  const { path } = await ctx.params;
  return forward(req, path, "POST");
}
