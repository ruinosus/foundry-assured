// Proxy for the backend HTML Artifacts API (/artifacts/html). Forwards the caller's Entra
// bearer token so the backend's require_role gate sees the user's roles. List + generate only —
// per-artifact reads/actions go through the [...path] catch-all.
import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";
const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

export async function GET(req: NextRequest) {
  try {
    const auth = req.headers.get("authorization");
    const r = await fetch(`${BACKEND}/artifacts/html`, {
      cache: "no-store",
      headers: auth ? { Authorization: auth } : undefined,
    });
    if (!r.ok) {
      return NextResponse.json({ artifacts: [], error: `backend ${r.status}` }, { status: 502 });
    }
    return NextResponse.json(await r.json());
  } catch {
    return NextResponse.json({ artifacts: [], error: "backend unreachable" }, { status: 502 });
  }
}

export async function POST(req: NextRequest) {
  try {
    const auth = req.headers.get("authorization");
    const r = await fetch(`${BACKEND}/artifacts/html/generate`, {
      method: "POST",
      cache: "no-store",
      headers: {
        "Content-Type": "application/json",
        ...(auth ? { Authorization: auth } : {}),
      },
      body: await req.text(),
    });
    const text = await r.text();
    return new NextResponse(text, {
      status: r.status,
      headers: { "Content-Type": "application/json" },
    });
  } catch {
    return NextResponse.json({ error: "backend unreachable" }, { status: 502 });
  }
}
