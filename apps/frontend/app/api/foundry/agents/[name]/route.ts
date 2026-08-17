// Detalhe do agente (versões + sessões) e as ações de escrita sobre ele.
//
// GET é leitura autenticada; POST e DELETE exigem Admin, re-checado no backend. Este proxy não
// decide autorização — só repassa o token. Confiar no frontend para autorizar seria o mesmo que
// não autorizar.
import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

/** Repassa método, corpo e token; devolve o motivo do backend quando falha. */
async function proxy(req: NextRequest, path: string, method: string, body?: unknown) {
  try {
    const auth = req.headers.get("authorization");
    const r = await fetch(`${BACKEND}${path}`, {
      method,
      cache: "no-store",
      headers: {
        ...(auth ? { Authorization: auth } : {}),
        ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      },
      ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      return NextResponse.json(
        { error: data?.detail ?? `backend ${r.status}` },
        { status: r.status === 401 || r.status === 403 ? r.status : r.status === 400 ? 400 : 502 },
      );
    }
    return NextResponse.json(data);
  } catch {
    return NextResponse.json({ error: "backend inacessível" }, { status: 502 });
  }
}

export async function GET(req: NextRequest, ctx: { params: Promise<{ name: string }> }) {
  const { name } = await ctx.params;
  return proxy(req, `/foundry/agents/${encodeURIComponent(name)}`, "GET");
}

export async function POST(req: NextRequest, ctx: { params: Promise<{ name: string }> }) {
  const { name } = await ctx.params;
  const body = await req.json().catch(() => ({}));
  // `action` decide a sub-rota: enable, disable ou publicar versão. Um POST só evita três
  // arquivos de rota para três variações do mesmo recurso.
  const action = String(body?.action ?? "");
  const base = `/foundry/agents/${encodeURIComponent(name)}`;
  if (action === "enable" || action === "disable") return proxy(req, `${base}/${action}`, "POST");
  return proxy(req, `${base}/versions`, "POST", body);
}

export async function DELETE(req: NextRequest, ctx: { params: Promise<{ name: string }> }) {
  const { name } = await ctx.params;
  return proxy(req, `/foundry/agents/${encodeURIComponent(name)}`, "DELETE");
}
