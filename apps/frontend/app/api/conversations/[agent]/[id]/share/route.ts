// Compartilhar/revogar/consultar o estado de uma conversa (backend /conversations/{agent}/{id}/share).
//
// Mesmo padrão dos outros proxies desta pasta: o token do chamador viaja, o backend decide posse
// (é ele quem sabe se o `agent`/`id` pertence a quem está pedindo) — esta rota não reimplementa
// nenhuma checagem, só repassa e traduz o status de erro.
import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

function alvo(agent: string, id: string): string {
  return `${BACKEND}/conversations/${encodeURIComponent(agent)}/${encodeURIComponent(id)}/share`;
}

async function encaminhar(
  req: NextRequest,
  { params }: { params: Promise<{ agent: string; id: string }> },
  method: "GET" | "POST" | "DELETE",
) {
  const { agent, id } = await params;
  try {
    const auth = req.headers.get("authorization");
    const r = await fetch(alvo(agent, id), {
      method,
      cache: "no-store",
      headers: auth ? { Authorization: auth } : undefined,
    });
    if (!r.ok) {
      return NextResponse.json(
        { shared: false, error: `backend ${r.status}` },
        { status: [401, 403, 404].includes(r.status) ? r.status : 502 },
      );
    }
    return NextResponse.json(await r.json());
  } catch {
    return NextResponse.json({ shared: false, error: "backend unreachable" }, { status: 502 });
  }
}

export async function GET(req: NextRequest, ctx: { params: Promise<{ agent: string; id: string }> }) {
  return encaminhar(req, ctx, "GET");
}

export async function POST(req: NextRequest, ctx: { params: Promise<{ agent: string; id: string }> }) {
  return encaminhar(req, ctx, "POST");
}

export async function DELETE(req: NextRequest, ctx: { params: Promise<{ agent: string; id: string }> }) {
  return encaminhar(req, ctx, "DELETE");
}
