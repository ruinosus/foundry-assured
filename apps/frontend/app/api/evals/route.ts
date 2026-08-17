// Proxies the backend's recorded eval runs to the /evals page (server-side fetch,
// so no CORS and the backend URL stays off the client). Forwards the caller's Entra
// bearer token so the (now auth-gated) backend endpoint accepts the request.
import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

export async function GET(req: NextRequest) {
  try {
    const auth = req.headers.get("authorization");
    const r = await fetch(`${BACKEND}/eval/foundry`, {
      cache: "no-store",
      headers: auth ? { Authorization: auth } : undefined,
    });
    if (!r.ok) {
      return NextResponse.json(
        {
          runs: [],
          error:
            r.status === 404
              ? "rota não encontrada no backend (ele está rodando código anterior a ela?)"
              : `backend ${r.status}`,
        },
        { status: r.status === 401 || r.status === 403 ? r.status : 502 },
      );
    }
    // O corpo traz `reason` quando a lista está vazia por FALHA — distinto de vazia porque não há
    // execução. A tela precisa dos dois para não dar o conselho errado.
    return NextResponse.json(await r.json());
  } catch {
    return NextResponse.json({ runs: [], error: "backend unreachable" }, { status: 502 });
  }
}
