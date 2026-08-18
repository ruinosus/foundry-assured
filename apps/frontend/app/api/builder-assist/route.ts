// Desfecho de proposta (POST) e as estatísticas do assistente (GET).
import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

function statusFor(s: number): number {
  return [400, 401, 403, 404].includes(s) ? s : 502;
}

export async function GET(req: NextRequest) {
  try {
    const auth = req.headers.get("authorization");
    const r = await fetch(`${BACKEND}/builder-assist/stats`, {
      cache: "no-store",
      headers: auth ? { Authorization: auth } : undefined,
    });
    const body = await r.json().catch(() => ({}));
    if (!r.ok) {
      return NextResponse.json(
        { error: body?.detail ?? `backend ${r.status}` },
        { status: statusFor(r.status) },
      );
    }
    return NextResponse.json(body);
  } catch {
    return NextResponse.json({ error: "backend unreachable" }, { status: 502 });
  }
}

export async function POST(req: NextRequest) {
  try {
    const auth = req.headers.get("authorization");
    const corpo = await req.json().catch(() => ({}));
    const r = await fetch(`${BACKEND}/builder-assist/proposals`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...(auth ? { Authorization: auth } : {}) },
      body: JSON.stringify(corpo),
    });
    // O desfecho é MEDIÇÃO, não parte do fluxo: uma falha aqui não pode impedir a pessoa de usar
    // ou descartar a proposta. A tela ignora o resultado; o servidor registra o que conseguir.
    return NextResponse.json(await r.json().catch(() => ({})), { status: r.ok ? 200 : 202 });
  } catch {
    return NextResponse.json({ recorded: false }, { status: 202 });
  }
}
