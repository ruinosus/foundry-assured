// Lista as conversas do usuário autenticado (backend /conversations).
//
// Não há `?user=` aqui nem no backend, de propósito: o dono da conversa é sempre quem está no
// token. Um parâmetro de usuário seria um IDOR pronto — bastaria trocar o id na URL.
import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

export async function GET(req: NextRequest) {
  const agent = req.nextUrl.searchParams.get("agent") ?? "";
  try {
    const auth = req.headers.get("authorization");
    const r = await fetch(
      `${BACKEND}/conversations${agent ? `?agent=${encodeURIComponent(agent)}` : ""}`,
      { cache: "no-store", headers: auth ? { Authorization: auth } : undefined },
    );
    if (!r.ok) {
      return NextResponse.json(
        { conversations: [], error: `backend ${r.status}` },
        // 401/403 passam com o próprio código: a tela precisa distinguir "não autenticado" de
        // "backend com problema", senão manda o usuário depurar o serviço errado.
        { status: r.status === 401 || r.status === 403 ? r.status : 502 },
      );
    }
    return NextResponse.json(await r.json());
  } catch {
    return NextResponse.json({ conversations: [], error: "backend unreachable" }, { status: 502 });
  }
}
