// As mensagens de uma conversa, para reabri-la na tela.
//
// O 404 do backend passa como 404 — não como 502. Conversa inexistente e conversa de outra pessoa
// respondem igual lá (dizer "existe mas não é sua" já vazaria a existência), e mapear isso para
// 502 mandaria a tela acusar o backend de estar quebrado.
import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ agent: string; id: string }> },
) {
  const { agent, id } = await params;
  try {
    const auth = req.headers.get("authorization");
    const r = await fetch(
      `${BACKEND}/conversations/${encodeURIComponent(agent)}/${encodeURIComponent(id)}`,
      { cache: "no-store", headers: auth ? { Authorization: auth } : undefined },
    );
    if (!r.ok) {
      return NextResponse.json(
        { messages: [], error: `backend ${r.status}` },
        { status: [401, 403, 404].includes(r.status) ? r.status : 502 },
      );
    }
    return NextResponse.json(await r.json());
  } catch {
    return NextResponse.json({ messages: [], error: "backend unreachable" }, { status: 502 });
  }
}
