// Repassa o catálogo de bases de conhecimento, com o token do chamador.
//
// Mesmo desenho do proxy de agentes ao lado: o browser não fala com o backend direto (origem
// diferente) e o token nunca sai do fluxo Entra.
import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

export async function GET(req: NextRequest) {
  try {
    const auth = req.headers.get("authorization");
    const r = await fetch(`${BACKEND}/foundry/knowledge`, {
      cache: "no-store",
      headers: auth ? { Authorization: auth } : undefined,
    });
    const body = await r.json().catch(() => ({}));
    if (!r.ok) {
      // O motivo do backend atravessa: "502" sozinho não diz se faltou permissão, se o serviço
      // do Search está desligado ou se a versão de API não tem as operações de knowledge.
      return NextResponse.json(
        { bases: [], sources: [], error: body?.detail ?? `backend ${r.status}` },
        { status: r.status === 401 ? 401 : 502 },
      );
    }
    return NextResponse.json(body);
  } catch {
    return NextResponse.json(
      { bases: [], sources: [], error: "backend inacessível" },
      { status: 502 },
    );
  }
}
