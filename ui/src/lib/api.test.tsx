import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { SWRConfig } from "swr";
import * as api from "./api";

const fetchMock = vi.fn();

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "content-type": "application/json" },
    ...init,
  });
}

function textResponse(body: string, init: ResponseInit = {}) {
  return new Response(body, { status: 200, headers: { "content-type": "text/plain" }, ...init });
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => vi.unstubAllGlobals());

describe("api()", () => {
  it("sends JSON headers and parses a JSON response", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ok: 1 }));
    await expect(api.api("/x", { headers: { "X-Extra": "1" } })).resolves.toEqual({ ok: 1 });
    expect(fetchMock).toHaveBeenCalledWith("/x", {
      headers: { "Content-Type": "application/json", "X-Extra": "1" },
    });
  });

  it("returns text for non-JSON responses", async () => {
    fetchMock.mockResolvedValue(textResponse("plain"));
    await expect(api.api("/x")).resolves.toBe("plain");
  });

  it("raises ApiError with a string detail", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: "nope" }, { status: 403 }));
    const err = (await api.api("/x").catch((e: unknown) => e)) as api.ApiError;
    expect(err).toBeInstanceOf(api.ApiError);
    expect(err.status).toBe(403);
    expect(err.message).toBe("nope");
  });

  it("stringifies a structured detail", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: [{ msg: "bad" }] }, { status: 422 }));
    await expect(api.api("/x")).rejects.toThrow('[{"msg":"bad"}]');
  });

  it("falls back to the status text for a non-JSON error body", async () => {
    fetchMock.mockResolvedValue(new Response("<html>", { status: 502, statusText: "Bad Gateway" }));
    await expect(api.api("/x")).rejects.toThrow("Bad Gateway");
  });
});

describe("mutations", () => {
  const cases: [string, () => Promise<unknown>, string, string, unknown?][] = [
    ["createApp", () => api.createApp({ slug: "s" } as never), "/api/v1/apps", "POST", { slug: "s" }],
    ["patchApp", () => api.patchApp("a1", { branch: "dev" }), "/api/v1/apps/a1", "PATCH", { branch: "dev" }],
    ["deleteApp", () => api.deleteApp("a1"), "/api/v1/apps/a1", "DELETE"],
    ["deployApp", () => api.deployApp("a1"), "/api/v1/apps/a1/deploy", "POST"],
    ["rebootApp", () => api.rebootApp("a1"), "/api/v1/apps/a1/reboot", "POST"],
    ["wakeApp", () => api.wakeApp("a1"), "/api/v1/apps/a1/wake", "POST"],
    ["requestScan", () => api.requestScan("a1"), "/api/v1/apps/a1/scan", "POST"],
    ["putSecrets", () => api.putSecrets("a1", "k = 1"), "/api/v1/apps/a1/secrets", "PUT", { secrets_toml: "k = 1" }],
    ["createToken", () => api.createToken({ name: "t" } as never), "/api/v1/me/tokens", "POST", { name: "t" }],
    ["revokeToken", () => api.revokeToken("t1"), "/api/v1/me/tokens/t1", "DELETE"],
  ];

  it.each(cases)("%s calls the right endpoint", async (_name, call, url, method, body) => {
    fetchMock.mockResolvedValue(jsonResponse({}));
    await call();
    const [calledUrl, init] = fetchMock.mock.calls[0];
    expect(calledUrl).toBe(url);
    expect(init.method).toBe(method);
    if (body !== undefined) expect(JSON.parse(init.body)).toEqual(body);
  });
});

describe("helpers", () => {
  it("builds an encoded login URL", () => {
    expect(api.loginUrl("/apps/a b")).toBe("/api/auth/login?next=%2Fapps%2Fa%20b");
  });

  it("logout navigates to the logout endpoint", () => {
    const assign = vi.fn();
    vi.stubGlobal("location", { ...window.location, assign });
    api.logout();
    expect(assign).toHaveBeenCalledWith("/api/auth/logout");
  });
});

describe("hooks", () => {
  const wrapper = ({ children }: { children: ReactNode }) => (
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>{children}</SWRConfig>
  );

  function respond(url: string) {
    return url.includes("/logs") || url.endsWith("/secrets")
      ? textResponse(`text:${url}`)
      : jsonResponse({ url });
  }

  beforeEach(() => {
    fetchMock.mockImplementation((url: string) => Promise.resolve(respond(url)));
  });

  const jsonHooks: [string, () => { data: unknown }, string][] = [
    ["useMe", () => api.useMe(), "/api/v1/me"],
    ["useGroups", () => api.useGroups(), "/api/v1/groups"],
    ["useGroups(q)", () => api.useGroups("a b"), "/api/v1/groups?q=a%20b"],
    ["useTags", () => api.useTags(), "/api/v1/tags"],
    ["useTags(q)", () => api.useTags("x"), "/api/v1/tags?q=x"],
    ["useApps", () => api.useApps(), "/api/v1/apps"],
    ["useApp", () => api.useApp("a1"), "/api/v1/apps/a1"],
    ["useBuilds", () => api.useBuilds("a1"), "/api/v1/apps/a1/builds"],
    ["useAppMetrics", () => api.useAppMetrics("a1"), "/api/v1/apps/a1/metrics"],
    ["useAppAnalytics", () => api.useAppAnalytics("a1"), "/api/v1/apps/a1/analytics"],
    ["useAdminOverview", () => api.useAdminOverview(), "/api/v1/admin/overview"],
    ["useActivity", () => api.useActivity(true, 5), "/api/v1/admin/activity?limit=5"],
    ["useAppScans", () => api.useAppScans("a1"), "/api/v1/apps/a1/scans"],
    ["useScanVulnerabilities", () => api.useScanVulnerabilities("a1", "s1"), "/api/v1/apps/a1/scans/s1/vulnerabilities"],
    ["useAdminScans", () => api.useAdminScans(), "/api/v1/admin/scans"],
    ["useAdminScanVulnerabilities", () => api.useAdminScanVulnerabilities("s1"), "/api/v1/admin/scans/s1/vulnerabilities"],
    ["useTokens", () => api.useTokens(), "/api/v1/me/tokens"],
  ];

  it.each(jsonHooks)("%s fetches its JSON endpoint", async (_name, hook, url) => {
    const { result } = renderHook(hook, { wrapper });
    await waitFor(() => expect(result.current.data).toEqual({ url }));
  });

  const textHooks: [string, () => { data: unknown }, string][] = [
    ["useAppLogs", () => api.useAppLogs("a1", true, 50), "/api/v1/apps/a1/logs?tail=50"],
    ["useAppLogs (no follow)", () => api.useAppLogs("a1", false), "/api/v1/apps/a1/logs?tail=500"],
    ["useBuildLogs", () => api.useBuildLogs("a1", "b1"), "/api/v1/apps/a1/builds/b1/logs"],
    ["useAdminLogs", () => api.useAdminLogs(10), "/api/v1/admin/logs?tail=10"],
    ["useSecrets", () => api.useSecrets("a1"), "/api/v1/apps/a1/secrets"],
  ];

  it.each(textHooks)("%s fetches its text endpoint", async (_name, hook, url) => {
    const { result } = renderHook(hook, { wrapper });
    await waitFor(() => expect(result.current.data).toBe(`text:${url}`));
  });

  it("text hooks surface HTTP errors", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: "gone" }, { status: 404 }));
    const { result } = renderHook(() => api.useSecrets("a1"), { wrapper });
    await waitFor(() => expect((result.current as { error?: Error }).error?.message).toBe("gone"));
  });

  it("disabled hooks don't fetch", () => {
    renderHook(
      () => {
        api.useAdminOverview(false);
        api.useActivity(false);
        api.useAdminScans(false);
        api.useBuildLogs("a1", null);
        api.useScanVulnerabilities("a1", null);
        api.useAdminScanVulnerabilities(null);
      },
      { wrapper },
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
