import type { NextRequest } from "next/server";

// Server-side forwarder to the control plane. Runs in the Node runtime, so
// CONTROL_PLANE_URL is read from the container environment at request time.

const HOP_BY_HOP = ["connection", "keep-alive", "transfer-encoding", "te", "upgrade"];

export async function forwardToControlPlane(
  req: NextRequest,
  pathPrefix: string,
  path: string[],
): Promise<Response> {
  const base = process.env.CONTROL_PLANE_URL ?? "http://localhost:8000";
  const url = new URL(`${pathPrefix}/${path.join("/")}${req.nextUrl.search}`, base);

  const headers = new Headers(req.headers);
  for (const h of HOP_BY_HOP) headers.delete(h);
  headers.set("x-forwarded-host", req.nextUrl.host);

  const upstream = await fetch(url, {
    method: req.method,
    headers,
    body: ["GET", "HEAD"].includes(req.method) ? undefined : req.body,
    redirect: "manual", // pass 3xx (OIDC login flows) through to the browser
    // @ts-expect-error -- required by undici when streaming a request body
    duplex: "half",
  });

  const respHeaders = new Headers(upstream.headers);
  // fetch already decoded the body; stale encoding/length headers would corrupt it
  respHeaders.delete("content-encoding");
  respHeaders.delete("content-length");
  for (const h of HOP_BY_HOP) respHeaders.delete(h);

  return new Response(upstream.body, {
    status: upstream.status,
    headers: respHeaders,
  });
}
