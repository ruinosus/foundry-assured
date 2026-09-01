import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

export async function POST(request: NextRequest) {
  try {
    const headers = new Headers({ "Content-Type": "application/json" });
    for (const name of ["authorization", "accept-language", "x-area-id"]) {
      const value = request.headers.get(name);
      if (value) headers.set(name, value);
    }
    const response = await fetch(`${BACKEND}/proposer/changeset`, {
      method: "POST",
      headers,
      body: await request.text(),
      cache: "no-store",
    });
    const body = await response.json().catch(() => ({}));
    return NextResponse.json(body, {
      status: response.ok ? response.status : [400, 401, 403, 404, 422].includes(response.status) ? response.status : 502,
    });
  } catch {
    return NextResponse.json({ error: { code: "BACKEND_UNAVAILABLE" } }, { status: 502 });
  }
}