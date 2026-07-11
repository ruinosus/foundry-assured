// Proxy for the backend admin API (/admin/*). Forwards the caller's Entra bearer token so
// the backend's server-side Admin gate sees the user's roles. The browser never calls Graph
// directly — it goes through here to the FastAPI backend, which holds the app-only Graph creds.
import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";
const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

async function proxy(req: NextRequest, path: string[]) {
  const auth = req.headers.get("authorization");
  const url = `${BACKEND}/admin/${path.join("/")}${req.nextUrl.search}`;
  const init: RequestInit = {
    method: req.method,
    cache: "no-store",
    headers: {
      ...(auth ? { Authorization: auth } : {}),
      "Content-Type": "application/json",
    },
  };
  if (req.method !== "GET" && req.method !== "DELETE") {
    init.body = await req.text();
  }
  try {
    const r = await fetch(url, init);
    const text = await r.text();
    return new NextResponse(text, {
      status: r.status,
      headers: { "Content-Type": "application/json" },
    });
  } catch {
    return NextResponse.json({ error: "backend unreachable" }, { status: 502 });
  }
}

type Ctx = { params: Promise<{ path: string[] }> };
export async function GET(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
export async function POST(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
export async function DELETE(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
