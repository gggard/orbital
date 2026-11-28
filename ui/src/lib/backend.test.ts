import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { NextRequest } from "next/server";
import { forwardToControlPlane } from "./backend";

const fetchMock = vi.fn();

function request(method: string, url: string, headers: Record<string, string> = {}, body?: string) {
  const u = new URL(url);
  return {
    method,
    headers: new Headers(headers),
    body: body ?? null,
    nextUrl: { search: u.search, host: u.host },
  } as unknown as NextRequest;
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("forwardToControlPlane", () => {
  it("forwards a GET to the control plane, dropping hop-by-hop headers", async () => {
    vi.stubEnv("CONTROL_PLANE_URL", "http://cp:9000");
    fetchMock.mockResolvedValue(
      new Response("ok", {
        status: 201,
        headers: {
          "content-type": "text/plain",
          "content-encoding": "gzip",
          "content-length": "2",
          connection: "keep-alive",
          "x-upstream": "1",
        },
      }),
    );

    const res = await forwardToControlPlane(
      request("GET", "https://ui.example.com/api/v1/apps?x=1", {
        connection: "keep-alive",
        cookie: "s=1",
      }),
      "/api/v1",
      ["apps"],
    );

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe("http://cp:9000/api/v1/apps?x=1");
    expect(init.method).toBe("GET");
    expect(init.body).toBeUndefined();
    expect(init.redirect).toBe("manual");
    expect(init.headers.get("connection")).toBeNull();
    expect(init.headers.get("cookie")).toBe("s=1");
    expect(init.headers.get("x-forwarded-host")).toBe("ui.example.com");

    expect(res.status).toBe(201);
    expect(res.headers.get("content-encoding")).toBeNull();
    expect(res.headers.get("content-length")).toBeNull();
    expect(res.headers.get("connection")).toBeNull();
    expect(res.headers.get("x-upstream")).toBe("1");
    expect(await res.text()).toBe("ok");
  });

  it("streams the body for non-GET methods and defaults the base URL", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    await forwardToControlPlane(
      request("POST", "https://ui.example.com/webhooks/a/t", {}, "payload"),
      "/webhooks",
      ["a", "t"],
    );
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe("http://localhost:8000/webhooks/a/t");
    expect(init.body).toBe("payload");
    expect(init.duplex).toBe("half");
  });
});
