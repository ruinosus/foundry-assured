// Uma skill: detalhe, publicação de versão (inline ou bundle) e exclusão.
//
// O bundle chega como multipart e é repassado como multipart — reserializar arquivo em JSON
// (base64) inflaria 33% e obrigaria a carregar tudo em memória duas vezes.
import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

/** Traduz o status do backend em vez de achatar tudo em 502 — 404 significa "rota não existe lá". */
function statusFor(backendStatus: number): number {
  if (backendStatus === 401 || backendStatus === 403) return backendStatus;
  if (backendStatus === 400) return 400;
  if (backendStatus === 404) return 404;
  return 502;
}

async function relay(r: Response) {
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    return NextResponse.json(
      {
        error:
          data?.detail ??
          (r.status === 404
            ? "rota não encontrada no backend (ele está rodando código anterior a ela?)"
            : `backend ${r.status}`),
      },
      { status: statusFor(r.status) },
    );
  }
  return NextResponse.json(data);
}

export async function GET(req: NextRequest, ctx: { params: Promise<{ name: string }> }) {
  const { name } = await ctx.params;
  const auth = req.headers.get("authorization");
  try {
    return relay(
      await fetch(`${BACKEND}/foundry/skills/${encodeURIComponent(name)}`, {
        cache: "no-store",
        headers: auth ? { Authorization: auth } : undefined,
      }),
    );
  } catch {
    return NextResponse.json({ error: "backend inacessível" }, { status: 502 });
  }
}

export async function POST(req: NextRequest, ctx: { params: Promise<{ name: string }> }) {
  const { name } = await ctx.params;
  const auth = req.headers.get("authorization");
  const contentType = req.headers.get("content-type") ?? "";
  const base = `/foundry/skills/${encodeURIComponent(name)}`;

  try {
    if (contentType.includes("multipart/form-data")) {
      const form = await req.formData();
      return relay(
        await fetch(`${BACKEND}${base}/files`, {
          method: "POST",
          headers: auth ? { Authorization: auth } : undefined,
          body: form,
        }),
      );
    }
    const body = await req.json().catch(() => ({}));
    return relay(
      await fetch(`${BACKEND}${base}`, {
        method: "POST",
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

export async function DELETE(req: NextRequest, ctx: { params: Promise<{ name: string }> }) {
  const { name } = await ctx.params;
  const auth = req.headers.get("authorization");
  try {
    return relay(
      await fetch(`${BACKEND}/foundry/skills/${encodeURIComponent(name)}`, {
        method: "DELETE",
        headers: auth ? { Authorization: auth } : undefined,
      }),
    );
  } catch {
    return NextResponse.json({ error: "backend inacessível" }, { status: 502 });
  }
}
