import { NextRequest } from "next/server";

const BACKEND = process.env.BACKEND_URL || "http://127.0.0.1:8000";
const KEY = process.env.GOVINTEL_API_KEY || "dev-local-key";

async function proxy(req: NextRequest, ctx: { params: { path: string[] } }) {
  const path = ctx.params.path.join("/");
  const url = `${BACKEND}/api/${path}${req.nextUrl.search}`;
  const init: RequestInit = {
    method: req.method,
    headers: { "X-API-Key": KEY, "Content-Type": "application/json" },
  };
  if (req.method !== "GET" && req.method !== "HEAD") init.body = await req.text();

  try {
    const res = await fetch(url, init);
    const body = await res.text();
    return new Response(body, {
      status: res.status,
      headers: { "Content-Type": res.headers.get("content-type") || "application/json" },
    });
  } catch {
    return new Response(
      JSON.stringify({ error: "backend_unreachable", detail: `Could not reach ${BACKEND}` }),
      { status: 502, headers: { "Content-Type": "application/json" } },
    );
  }
}

export { proxy as GET, proxy as POST };
