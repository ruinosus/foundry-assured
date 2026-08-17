// Qual project do Foundry este ambiente usa.
//
// Existe porque todos os recursos vivem dentro de um project, e a interface não dizia qual — quem
// olha uma lista vazia não sabe se não há nada ou se está olhando o lugar errado.
import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

export async function GET(req: NextRequest) {
  try {
    const auth = req.headers.get("authorization");
    const r = await fetch(`${BACKEND}/foundry/project`, {
      cache: "no-store",
      headers: auth ? { Authorization: auth } : undefined,
    });
    const body = await r.json().catch(() => ({}));
    // Falha aqui não é erro de tela: o rótulo do project some e o resto do app continua. Um
    // cabeçalho não é motivo para derrubar a navegação.
    if (!r.ok) return NextResponse.json({ name: null, host: null }, { status: 200 });
    return NextResponse.json(body);
  } catch {
    return NextResponse.json({ name: null, host: null }, { status: 200 });
  }
}
