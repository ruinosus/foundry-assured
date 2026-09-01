import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

function statusFor(status: number): number {
  return [400, 401, 403, 404, 409, 422].includes(status) ? status : 502;
}

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const { path } = await context.params;
  const targetPath = path.map(encodeURIComponent).join("/");
  const headers = new Headers();
  for (const name of ["authorization", "x-area-id", "accept-language"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }

  try {
    const response = await fetch(
      `${BACKEND}/authoring/${targetPath}${request.nextUrl.search}`,
      { cache: "no-store", headers },
    );
    const body = await response.json().catch(() => ({}));
    return NextResponse.json(body, { status: response.ok ? response.status : statusFor(response.status) });
  } catch {
    return NextResponse.json(
      { error: { code: "BACKEND_UNAVAILABLE", message: "Backend indisponível." } },
      { status: 502 },
    );
  }
}