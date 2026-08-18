// Rascunho de agente (backend /proposer/draft). NÃO publica nada — devolve um formulário.
//
// O `Accept-Language` é repassado: sem ele o rascunho nasce em inglês para quem está com a tela
// em português, porque a requisição sai do SERVIDOR Next e não carrega o idioma do navegador.
import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

export async function POST(req: NextRequest) {
  try {
    const auth = req.headers.get("authorization");
    const idioma = req.headers.get("accept-language");
    const corpo = await req.json().catch(() => ({}));
    const r = await fetch(`${BACKEND}/proposer/draft`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(auth ? { Authorization: auth } : {}),
        ...(idioma ? { "Accept-Language": idioma } : {}),
      },
      body: JSON.stringify(corpo),
    });
    const body = await r.json().catch(() => ({}));
    if (!r.ok) {
      return NextResponse.json(
        { error: body?.detail ?? `backend ${r.status}` },
        { status: [400, 401, 403, 404].includes(r.status) ? r.status : 502 },
      );
    }
    return NextResponse.json(body);
  } catch {
    return NextResponse.json({ error: "backend unreachable" }, { status: 502 });
  }
}
