// Proxies the backend's recorded eval runs to the /evals page (server-side fetch,
// so no CORS and the backend URL stays off the client).
import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

export async function GET() {
  try {
    const r = await fetch(`${BACKEND}/eval/runs`, { cache: "no-store" });
    if (!r.ok) {
      return NextResponse.json({ runs: [], error: `backend ${r.status}` }, { status: 502 });
    }
    return NextResponse.json(await r.json());
  } catch {
    return NextResponse.json({ runs: [], error: "backend unreachable" }, { status: 502 });
  }
}
