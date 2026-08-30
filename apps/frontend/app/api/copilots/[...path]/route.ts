// Repassa a leitura de copilotos, com o token do chamador.
//
// Mesmo desenho dos outros proxies em app/api/: o browser não fala com o backend direto (origem
// diferente) e o token nunca sai do fluxo Entra. 404 e 422 atravessam intactos — "não existe" e
// "existe e está torto" pedem ações diferentes de quem lê.
import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

export async function GET(req: NextRequest, { params }: { params: Promise<{ path?: string[] }> }) {
  const { path } = await params;
  const sufixo = (path ?? []).map(encodeURIComponent).join("/");
  try {
    const auth = req.headers.get("authorization");
    const r = await fetch(`${BACKEND}/copilots${sufixo ? `/${sufixo}` : ""}`, {
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
