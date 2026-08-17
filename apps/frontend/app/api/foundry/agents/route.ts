// Repassa o catálogo de agentes do Foundry, com o token do chamador.
//
// O backend valida o token e chama o SDK com a identidade da aplicação; este proxy existe
// porque o browser não fala com o backend direto (origem diferente) e porque o token nunca
// deve sair do fluxo Entra.
import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

export async function GET(req: NextRequest) {
  try {
    const auth = req.headers.get("authorization");
    const r = await fetch(`${BACKEND}/foundry/agents`, {
      cache: "no-store",
      headers: auth ? { Authorization: auth } : undefined,
    });
    const body = await r.json().catch(() => ({}));
    if (!r.ok) {
      // Repassa o motivo do backend em vez de um genérico: "502" sozinho não diz se faltou
      // permissão, se o projeto não existe ou se o serviço caiu.
      return NextResponse.json(
        { agents: [], error: body?.detail ?? `backend ${r.status}` },
        { status: r.status === 401 ? 401 : 502 },
      );
    }
    return NextResponse.json(body);
  } catch {
    return NextResponse.json({ agents: [], error: "backend inacessível" }, { status: 502 });
  }
}
