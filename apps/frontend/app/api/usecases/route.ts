// Casos de uso — a camada de negócio sobre os agentes.
import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

export async function GET(req: NextRequest) {
  try {
    const auth = req.headers.get("authorization");
    const r = await fetch(`${BACKEND}/usecases`, {
      cache: "no-store",
      headers: auth ? { Authorization: auth } : undefined,
    });
    const body = await r.json().catch(() => ({}));
    if (!r.ok) {
      return NextResponse.json(
        { use_cases: [], error: body?.detail ?? `backend ${r.status}` },
        { status: r.status === 401 ? 401 : 502 },
      );
    }
    return NextResponse.json(body);
  } catch {
    return NextResponse.json({ use_cases: [], error: "backend inacessível" }, { status: 502 });
  }
}
