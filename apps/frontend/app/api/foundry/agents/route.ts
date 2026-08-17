// Repassa o catálogo de agentes do Foundry, com o token do chamador.
//
// O backend valida o token e chama o SDK com a identidade da aplicação; este proxy existe
// porque o browser não fala com o backend direto (origem diferente) e porque o token nunca
// deve sair do fluxo Entra.
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
    const r = await fetch(`${BACKEND}/foundry/agents`, {
      cache: "no-store",
      headers: auth ? { Authorization: auth } : undefined,
    });
    const body = await r.json().catch(() => ({}));
    if (!r.ok) {
      // Repassa o motivo do backend em vez de um genérico: "502" sozinho não diz se faltou
      // permissão, se o projeto não existe ou se o serviço caiu.
      return NextResponse.json(
        { agents: [], error: body?.detail ?? (r.status === 404 ? "rota não encontrada no backend (ele está rodando código anterior a ela?)" : `backend ${r.status}`) },
        { status: statusFor(r.status) },
      );
    }
    return NextResponse.json(body);
  } catch {
    return NextResponse.json({ agents: [], error: "backend inacessível" }, { status: 502 });
  }
}
