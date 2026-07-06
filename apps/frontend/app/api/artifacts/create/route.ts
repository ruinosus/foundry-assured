// Create-from-html proxy for the Artifacts Studio's "Save as draft" — forwards the caller's
// Entra bearer token to POST /artifacts/html (Author/Admin gated backend-side). A separate
// path from /api/artifacts (which proxies to /generate) so the one-shot generate flow is
// untouched.
import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";
const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

export async function POST(req: NextRequest) {
  try {
    const auth = req.headers.get("authorization");
    const r = await fetch(`${BACKEND}/artifacts/html`, {
      method: "POST",
      cache: "no-store",
      headers: { "Content-Type": "application/json", ...(auth ? { Authorization: auth } : {}) },
      body: await req.text(),
    });
    return new NextResponse(await r.text(), {
      status: r.status,
      headers: { "Content-Type": "application/json" },
    });
  } catch {
    return NextResponse.json({ error: "backend unreachable" }, { status: 502 });
  }
}
