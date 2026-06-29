// Proxy for the backend /me — the signed-in caller's identity + app roles (used to gate the
// admin UI). Forwards the Entra bearer token.
import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";
const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

export async function GET(req: NextRequest) {
  const auth = req.headers.get("authorization");
  try {
    const r = await fetch(`${BACKEND}/me`, {
      cache: "no-store",
      headers: auth ? { Authorization: auth } : undefined,
    });
    return NextResponse.json(await r.json(), { status: r.status });
  } catch {
    return NextResponse.json({ roles: [], error: "backend unreachable" }, { status: 502 });
  }
}
