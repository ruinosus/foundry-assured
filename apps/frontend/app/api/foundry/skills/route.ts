// Catálogo de skills, com o token do chamador.
import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

export async function GET(req: NextRequest) {
  try {
    const auth = req.headers.get("authorization");
    const r = await fetch(`${BACKEND}/foundry/skills`, {
      cache: "no-store",
      headers: auth ? { Authorization: auth } : undefined,
    });
    const body = await r.json().catch(() => ({}));
    if (!r.ok) {
      return NextResponse.json(
        { skills: [], error: body?.detail ?? `backend ${r.status}` },
        { status: r.status === 401 ? 401 : 502 },
      );
    }
    return NextResponse.json(body);
  } catch {
    return NextResponse.json({ skills: [], error: "backend inacessível" }, { status: 502 });
  }
}

export async function POST(req: NextRequest) {
  try {
    const auth = req.headers.get("authorization");
    const body = await req.json().catch(() => ({}));
    // O nome vai no corpo e viaja para a sub-rota: `POST /skills/{name}` é o que o backend expõe,
    // porque criar e versionar são a mesma operação (a primeira versão é a criação).
    const name = String(body?.name ?? "");
    const r = await fetch(`${BACKEND}/foundry/skills/${encodeURIComponent(name)}`, {
      method: "POST",
      headers: {
        ...(auth ? { Authorization: auth } : {}),
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      return NextResponse.json(
        { error: data?.detail ?? `backend ${r.status}` },
        { status: r.status === 401 || r.status === 403 ? r.status : r.status === 400 ? 400 : 502 },
      );
    }
    return NextResponse.json(data);
  } catch {
    return NextResponse.json({ error: "backend inacessível" }, { status: 502 });
  }
}
