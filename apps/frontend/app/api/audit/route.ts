// Proxy da trilha de auditoria. Uma rota, com `op` na querystring, porque as quatro operações
// compartilham o mesmo repasse e a mesma tradução de status.
//
// O PACOTE volta como binário: `Content-Type: application/zip` atravessa intacto, porque o
// arquivo é o produto — reembalá-lo em JSON obrigaria o navegador a remontá-lo, e um pacote de
// auditoria remontado pelo cliente é um pacote que ninguém consegue afirmar que é o original.
import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

function statusFor(s: number): number {
  return [400, 401, 403, 404, 409].includes(s) ? s : 502;
}

export async function GET(req: NextRequest) {
  const p = req.nextUrl.searchParams;
  const op = p.get("op") ?? "report";
  const scope = p.get("scope") ?? "";
  const alvo =
    op === "trail"
      ? `/audit/trail/${encodeURIComponent(scope)}`
      : op === "anchors"
        ? `/audit/anchors/${encodeURIComponent(scope)}`
        : op === "package"
          ? "/audit/package"
          : "/audit/report";

  try {
    const auth = req.headers.get("authorization");
    const r = await fetch(`${BACKEND}${alvo}`, {
      cache: "no-store",
      headers: auth ? { Authorization: auth } : undefined,
    });

    if (op === "package") {
      if (!r.ok) {
        return NextResponse.json({ error: `backend ${r.status}` }, { status: statusFor(r.status) });
      }
      return new NextResponse(await r.arrayBuffer(), {
        headers: {
          "Content-Type": "application/zip",
          "Content-Disposition": 'attachment; filename="diligencia.zip"',
        },
      });
    }

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
  const scope = req.nextUrl.searchParams.get("scope") ?? "";
  try {
    const auth = req.headers.get("authorization");
    const r = await fetch(`${BACKEND}/audit/anchors/${encodeURIComponent(scope)}`, {
      method: "POST",
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
