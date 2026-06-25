// Proxies the real tickets opened by the HITL approval flow (backend create_ticket
// tool) to the /tickets page.
import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

export async function GET() {
  try {
    const r = await fetch(`${BACKEND}/tickets`, { cache: "no-store" });
    if (!r.ok) {
      return NextResponse.json({ tickets: [], error: `backend ${r.status}` }, { status: 502 });
    }
    return NextResponse.json(await r.json());
  } catch {
    return NextResponse.json({ tickets: [], error: "backend unreachable" }, { status: 502 });
  }
}
