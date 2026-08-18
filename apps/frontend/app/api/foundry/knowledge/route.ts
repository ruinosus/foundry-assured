// Repassa o catálogo de bases de conhecimento, com o token do chamador.
//
// Mesmo desenho do proxy de agentes ao lado: o browser não fala com o backend direto (origem
// diferente) e o token nunca sai do fluxo Entra.
import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

/** Traduz o status do backend em vez de achatar tudo em 502.
 *
 * 404 é o caso que custou tempo: significa "esta rota não existe no backend", quase sempre porque
 * o processo está rodando código anterior à rota. Devolver 502 ("Bad Gateway") mandava procurar
 * falha de serviço quando bastava reiniciar o backend. Agora a mensagem diz isso.
 */
function statusFor(backendStatus: number): number {
  if (backendStatus === 401 || backendStatus === 403) return backendStatus;
  if (backendStatus === 400) return 400;
  if (backendStatus === 404) return 404;
  return 502;
}

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
        { bases: [], sources: [], error: body?.detail ?? (r.status === 404 ? "rota não encontrada no backend (ele está rodando código anterior a ela?)" : `backend ${r.status}`) },
        { status: statusFor(r.status) },
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

export async function POST(req: NextRequest) {
  try {
    const auth = req.headers.get("authorization");
    const body = await req.json().catch(() => ({}));
    const r = await fetch(`${BACKEND}/foundry/knowledge`, {
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
        { error: data?.detail ?? (r.status === 404 ? "rota não encontrada no backend (ele está rodando código anterior a ela?)" : `backend ${r.status}`) },
        { status: statusFor(r.status) },
      );
    }
    return NextResponse.json(data);
  } catch {
    return NextResponse.json({ error: "backend inacessível" }, { status: 502 });
  }
}
