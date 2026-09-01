import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

function statusFor(status: number): number {
  return [400, 401, 403, 404, 409, 412, 422].includes(status) ? status : 502;
}

async function proxy(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const { path } = await context.params;
  const targetPath = path.map(encodeURIComponent).join("/");
  const headers = new Headers();
  for (const name of ["authorization", "x-area-id", "accept-language", "idempotency-key", "if-match", "content-type"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }

  try {
    const body = request.method === "GET" ? undefined : await request.text();
    const response = await fetch(
      `${BACKEND}/authoring/${targetPath}${request.nextUrl.search}`,
      { method: request.method, body, cache: "no-store", headers },
    );
    const responseBody = await response.json().catch(() => ({}));
    const responseHeaders = new Headers({ "Cache-Control": "no-store" });
    const etag = response.headers.get("etag");
    if (etag) responseHeaders.set("ETag", etag);
    return NextResponse.json(responseBody, {
      status: response.ok ? response.status : statusFor(response.status),
      headers: responseHeaders,
    });
  } catch {
    return NextResponse.json(
      { error: { code: "BACKEND_UNAVAILABLE", message: "Backend indisponível." } },
      { status: 502 },
    );
  }
}

export const GET = proxy;
export const POST = proxy;
export const PATCH = proxy;