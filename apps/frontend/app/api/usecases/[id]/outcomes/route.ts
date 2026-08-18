// Resultados de um caso de uso.
//
// POST e não GET porque a premissa (minutos por atendimento, custo da hora) vai no CORPO: numa
// querystring ela entraria no log de acesso e no histórico do browser, e "custo da hora da
// equipe" é dado que a empresa não escolheu publicar.
import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

export async function POST(req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const auth = req.headers.get("authorization");
  const body = await req.json().catch(() => ({}));
  try {
    const r = await fetch(`${BACKEND}/usecases/${encodeURIComponent(id)}/outcomes`, {
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
        { status: r.status === 401 || r.status === 403 || r.status === 400 ? r.status : 502 },
      );
    }
    return NextResponse.json(data);
  } catch {
    return NextResponse.json({ error: "backend inacessível" }, { status: 502 });
  }
}
