// Repassa o manifesto do formulário, com o token do chamador.
//
// Mesmo desenho dos outros proxies em app/api/: o browser não fala com o backend direto (origem
// diferente) e o token nunca sai do fluxo Entra.
//
// 404 E 422 ATRAVESSAM INTACTOS, e a distinção é o que a tela usa: "não existe formulário com
// esse nome" é outra coisa que "o formulário existe e está torto". Achatar os dois num 502 faria
// um erro de edição do manifesto parecer indisponibilidade do backend, e alguém tentaria de novo
// em vez de corrigir o documento.
import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

export async function GET(req: NextRequest, { params }: { params: Promise<{ name: string }> }) {
  const { name } = await params;
  try {
    const auth = req.headers.get("authorization");
    const r = await fetch(`${BACKEND}/flows/${encodeURIComponent(name)}`, {
      cache: "no-store",
      headers: auth ? { Authorization: auth } : undefined,
    });
    const body = await r.json().catch(() => ({}));
    const status = [401, 403, 404, 422].includes(r.status) ? r.status : r.ok ? 200 : 502;
    return NextResponse.json(body, { status });
  } catch {
    return NextResponse.json({ error: "backend unreachable" }, { status: 502 });
  }
}
