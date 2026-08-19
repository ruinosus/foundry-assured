// Repassa o documento citado, com o token do chamador.
//
// Mesmo desenho dos outros proxies em app/api/: o browser não fala com o backend direto
// (origem diferente) e o token nunca sai do fluxo Entra.
//
// 403 E 404 ATRAVESSAM INTACTOS, e isso importa: a tela precisa distinguir "você não tem
// acesso" de "não existe". Achatar os dois em 502 transformaria uma negativa de autorização
// — que é informação legítima para o usuário — em erro de infraestrutura.
import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

function statusFor(backendStatus: number): number {
  if (backendStatus === 401 || backendStatus === 403) return backendStatus;
  if (backendStatus === 400) return 400;
  if (backendStatus === 404) return 404;
  return 502;
}

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ domain: string; name: string }> },
) {
  const { domain, name } = await params;
  try {
    const auth = req.headers.get("authorization");
    const r = await fetch(
      `${BACKEND}/source/${encodeURIComponent(domain)}/${encodeURIComponent(name)}`,
      { cache: "no-store", headers: auth ? { Authorization: auth } : undefined },
    );
    const body = await r.json().catch(() => ({}));
    if (!r.ok) {
      return NextResponse.json(
        { error: body?.detail ?? `backend ${r.status}` },
        { status: statusFor(r.status) },
      );
    }
    return NextResponse.json(body);
  } catch {
    return NextResponse.json({ error: "backend inacessível" }, { status: 502 });
  }
}
