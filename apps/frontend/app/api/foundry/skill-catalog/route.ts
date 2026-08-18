// Catálogos públicos de skills — listar, ver e importar.
//
// Uma rota só, com `op` na querystring, porque as três operações compartilham o mesmo
// repassamento e a mesma tradução de status. O TOKEN do GitHub, quando houver, viaja no CORPO do
// POST — nunca em querystring (NORDOR-122: dado sensível não trafega em URL, que vai para log,
// trace e APM).
import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

/** 404 aqui quase sempre é "o backend está rodando código anterior a esta rota", não falha de
 *  serviço — achatar em 502 mandava procurar no lugar errado. */
function statusFor(s: number): number {
  if ([400, 401, 403, 404].includes(s)) return s;
  return 502;
}

export async function GET(req: NextRequest) {
  const p = req.nextUrl.searchParams;
  const op = p.get("op") ?? "list";
  const alvo =
    op === "catalogs"
      ? "/foundry/skill-catalogs"
      : op === "preview"
        ? `/foundry/skill-catalog/preview?repo=${encodeURIComponent(p.get("repo") ?? "")}&path=${encodeURIComponent(p.get("path") ?? "")}&ref=${encodeURIComponent(p.get("ref") ?? "main")}`
        : `/foundry/skill-catalog?repo=${encodeURIComponent(p.get("repo") ?? "")}&ref=${encodeURIComponent(p.get("ref") ?? "main")}`;

  try {
    const auth = req.headers.get("authorization");
    const r = await fetch(`${BACKEND}${alvo}`, {
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
    const r = await fetch(`${BACKEND}/foundry/skill-catalog/import`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(auth ? { Authorization: auth } : {}),
      },
      body: JSON.stringify(corpo),
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
