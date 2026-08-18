// Detalhe de uma base (status por fonte) e as ações de escrita sobre ela.
//
// Escrita exige Admin, re-checado no backend. O upload de arquivos e a importação do GitHub
// passam por aqui porque o browser não fala com o backend direto.
import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

/** Traduz o status do backend em vez de achatar tudo em 502.
 *
 * 404 é o caso que custou tempo: significa "esta rota não existe no backend", quase sempre porque
 * o processo está rodando código anterior à rota. Devolver 502 ("Bad Gateway") mandava procurar
 * falha de serviço quando bastava reiniciar o backend. Agora a mensagem diz isso.
 */
function statusFor(backendStatus: number): number {
  if (backendStatus === 401 || backendStatus === 403) return backendStatus;
  if (backendStatus === 400) return 400;
  if (backendStatus === 404) return 404;
  return 502;
}

function fail(status: number, error: string) {
  return NextResponse.json({ error }, { status });
}

async function relay(r: Response) {
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    return fail(
      r.status === 401 || r.status === 403 ? r.status : r.status === 400 ? 400 : 502,
      data?.detail ?? (r.status === 404 ? "rota não encontrada no backend (ele está rodando código anterior a ela?)" : `backend ${r.status}`),
    );
  }
  return NextResponse.json(data);
}

export async function GET(req: NextRequest, ctx: { params: Promise<{ name: string }> }) {
  const { name } = await ctx.params;
  try {
    const auth = req.headers.get("authorization");
    return relay(
      await fetch(`${BACKEND}/foundry/knowledge/${encodeURIComponent(name)}`, {
        cache: "no-store",
        headers: auth ? { Authorization: auth } : undefined,
      }),
    );
  } catch {
    return fail(502, "backend inacessível");
  }
}

export async function POST(req: NextRequest, ctx: { params: Promise<{ name: string }> }) {
  const { name } = await ctx.params;
  const base = `/foundry/knowledge/${encodeURIComponent(name)}`;
  const auth = req.headers.get("authorization");
  const contentType = req.headers.get("content-type") ?? "";

  try {
    // Upload chega como multipart e é repassado como multipart: reserializar o arquivo em JSON
    // (base64) inflaria 33% e obrigaria a carregar tudo em memória duas vezes.
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
    // O token do GitHub vai no CORPO, nunca na URL — querystring entra em log de acesso,
    // telemetria e histórico do browser.
    return relay(
      await fetch(`${BACKEND}${base}/github`, {
        method: "POST",
        headers: {
          ...(auth ? { Authorization: auth } : {}),
          "Content-Type": "application/json",
        },
        body: JSON.stringify(body),
      }),
    );
  } catch {
    return fail(502, "backend inacessível");
  }
}

export async function DELETE(req: NextRequest, ctx: { params: Promise<{ name: string }> }) {
  const { name } = await ctx.params;
  const auth = req.headers.get("authorization");
  // `delete_container` é decisão explícita de quem chama: apagar índice é reversível, apagar os
  // documentos originais não.
  const withFiles = new URL(req.url).searchParams.get("files") === "1";
  try {
    return relay(
      await fetch(
        `${BACKEND}/foundry/knowledge/${encodeURIComponent(name)}?delete_container=${withFiles}`,
        { method: "DELETE", headers: auth ? { Authorization: auth } : undefined },
      ),
    );
  } catch {
    return fail(502, "backend inacessível");
  }
}
