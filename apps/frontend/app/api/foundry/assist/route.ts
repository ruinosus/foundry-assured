// Sugestão para um campo do wizard. A resposta é PROPOSTA — a tela mostra e a pessoa decide.
//
// `Accept-Language` é repassado porque a sugestão sai no idioma da interface: um campo em
// português recebendo texto em inglês seria pior que campo vazio.
import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

export async function POST(req: NextRequest) {
  try {
    const auth = req.headers.get("authorization");
    const lang = req.headers.get("accept-language");
    const body = await req.json().catch(() => ({}));
    const r = await fetch(`${BACKEND}/foundry/assist`, {
      method: "POST",
      headers: {
        ...(auth ? { Authorization: auth } : {}),
        ...(lang ? { "Accept-Language": lang } : {}),
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      return NextResponse.json(
        { error: data?.detail ?? `backend ${r.status}` },
        {
          status:
            r.status === 401 || r.status === 403 ? r.status : r.status === 400 ? 400 : 502,
        },
      );
    }
    return NextResponse.json(data);
  } catch {
    return NextResponse.json({ error: "backend inacessível" }, { status: 502 });
  }
}
