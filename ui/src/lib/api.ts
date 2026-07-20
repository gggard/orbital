"use client";

import useSWR from "swr";
import type {
  AdminOverviewOut,
  AnalyticsOut,
  AppCreate,
  AppOut,
  AppUpdate,
  BuildOut,
  Me,
  MetricsOut,
} from "./types";

export class ApiError extends Error {
  status: number;
  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
  }
}

async function raise(res: Response): Promise<never> {
  let detail = res.statusText;
  try {
    const body = await res.json();
    if (typeof body.detail === "string") detail = body.detail;
    else if (body.detail) detail = JSON.stringify(body.detail);
  } catch {
    /* non-JSON error body */
  }
  throw new ApiError(res.status, detail);
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) await raise(res);
  return res.headers.get("content-type")?.includes("json")
    ? res.json()
    : (res.text() as Promise<T>);
}

const jsonFetcher = (url: string) => api<never>(url);
const textFetcher = async (url: string) => {
  const res = await fetch(url);
  if (!res.ok) await raise(res);
  return res.text();
};

// -- hooks -----------------------------------------------------------------

export const useMe = () =>
  useSWR<Me, ApiError>("/api/v1/me", jsonFetcher, {
    shouldRetryOnError: false,
    revalidateOnFocus: false,
  });

export const loginUrl = (next: string) =>
  `/api/auth/login?next=${encodeURIComponent(next)}`;

// full navigation: the browser must visit the IdP's end-session endpoint so
// the Keycloak SSO cookie is cleared too, not just our session
export const logout = () => window.location.assign("/api/auth/logout");

// known group directory for group pickers (role config + ORBITAL_KNOWN_GROUPS
// + optional live Keycloak lookup); advisory — free text is still allowed.
// q narrows server-side (case-insensitive substring) for large directories.
export const useGroups = (q = "") =>
  useSWR<{ groups: string[] }>(
    `/api/v1/groups${q ? `?q=${encodeURIComponent(q)}` : ""}`,
    jsonFetcher,
    {
      revalidateOnFocus: false,
      dedupingInterval: 60000,
      keepPreviousData: true,
    },
  );

export const useApps = () =>
  useSWR<AppOut[]>("/api/v1/apps", jsonFetcher, { refreshInterval: 4000 });

export const useApp = (id: string) =>
  useSWR<AppOut>(`/api/v1/apps/${id}`, jsonFetcher, {
    refreshInterval: 4000,
    shouldRetryOnError: false,
  });

export const useBuilds = (id: string) =>
  useSWR<BuildOut[]>(`/api/v1/apps/${id}/builds`, jsonFetcher, {
    refreshInterval: 5000,
  });

export const useAppLogs = (id: string, follow: boolean, tail = 500) =>
  useSWR<string>(`/api/v1/apps/${id}/logs?tail=${tail}`, textFetcher, {
    refreshInterval: follow ? 3000 : 0,
    keepPreviousData: true,
  });

export const useBuildLogs = (appId: string, buildId: string | null) =>
  useSWR<string>(
    buildId ? `/api/v1/apps/${appId}/builds/${buildId}/logs` : null,
    textFetcher,
    { refreshInterval: 4000, keepPreviousData: true },
  );

export const useAppMetrics = (id: string) =>
  useSWR<MetricsOut>(`/api/v1/apps/${id}/metrics`, jsonFetcher, {
    refreshInterval: 10000,
    keepPreviousData: true,
  });

export const useAppAnalytics = (id: string) =>
  useSWR<AnalyticsOut>(`/api/v1/apps/${id}/analytics`, jsonFetcher, {
    refreshInterval: 30000,
    keepPreviousData: true,
  });

export const useAdminOverview = () =>
  useSWR<AdminOverviewOut>("/api/v1/admin/overview", jsonFetcher, {
    refreshInterval: 5000,
    keepPreviousData: true,
  });

export const useAdminLogs = (tail = 500) =>
  useSWR<string>(`/api/v1/admin/logs?tail=${tail}`, textFetcher, {
    refreshInterval: 4000,
    keepPreviousData: true,
  });

export const useSecrets = (id: string) =>
  useSWR<string>(`/api/v1/apps/${id}/secrets`, textFetcher, {
    revalidateOnFocus: false,
  });

// -- mutations -------------------------------------------------------------

export const createApp = (body: AppCreate) =>
  api<AppOut>("/api/v1/apps", { method: "POST", body: JSON.stringify(body) });

export const patchApp = (id: string, body: AppUpdate) =>
  api<AppOut>(`/api/v1/apps/${id}`, { method: "PATCH", body: JSON.stringify(body) });

export const deleteApp = (id: string) =>
  api(`/api/v1/apps/${id}`, { method: "DELETE" });

export const deployApp = (id: string) =>
  api(`/api/v1/apps/${id}/deploy`, { method: "POST" });

export const rebootApp = (id: string) =>
  api(`/api/v1/apps/${id}/reboot`, { method: "POST" });

export const wakeApp = (id: string) =>
  api(`/api/v1/apps/${id}/wake`, { method: "POST" });

export const putSecrets = (id: string, secrets_toml: string) =>
  api(`/api/v1/apps/${id}/secrets`, {
    method: "PUT",
    body: JSON.stringify({ secrets_toml }),
  });
