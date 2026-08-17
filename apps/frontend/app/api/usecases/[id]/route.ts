// Um caso de uso: ler, renomear, e gravar o fluxo.
//
// O fluxo viaja como YAML CRU. O canvas serializa para a linguagem da Microsoft, e é isso que se
// grava — envelopar num objeto nosso criaria um formato intermediário que nenhuma outra
// ferramenta lê, e o YAML deixaria de ser portável.
import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

function statusFor(s: number): number {
  if (s === 401 || s === 403 || s === 404 || s === 400) return s;
  return 502;
}

async function relay(r: Response) {
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    return NextResponse.json(
      { error: data?.detail ?? `backend ${r.status}` },
      { status: statusFor(r.status) },
    );
  }
  return NextResponse.json(data);
}

export async function GET(req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const auth = req.headers.get("authorization");
  try {
    return relay(
      await fetch(`${BACKEND}/usecases/${encodeURIComponent(id)}`, {
        cache: "no-store",
        headers: auth ? { Authorization: auth } : undefined,
      }),
    );
  } catch {
    return NextResponse.json({ error: "backend inacessível" }, { status: 502 });
  }
}

export async function PUT(req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const auth = req.headers.get("authorization");
  const body = await req.json().catch(() => ({}));
  const base = `${BACKEND}/usecases/${encodeURIComponent(id)}`;
  try {
    // `yaml` no corpo distingue as duas operações sem inventar uma rota: renomear manda nome,
    // gravar fluxo manda YAML.
    const alvo = typeof body?.yaml === "string" ? `${base}/flow` : base;
    return relay(
      await fetch(alvo, {
        method: "PUT",
        headers: {
          ...(auth ? { Authorization: auth } : {}),
          "Content-Type": "application/json",
        },
        body: JSON.stringify(body),
      }),
    );
  } catch {
    return NextResponse.json({ error: "backend inacessível" }, { status: 502 });
  }
}
