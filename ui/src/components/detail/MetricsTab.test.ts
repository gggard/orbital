import { describe, expect, it } from "vitest";
import { restartsSummary } from "./MetricsTab";
import type { RestartInfo } from "@/lib/types";

function info(overrides: Partial<RestartInfo>): RestartInfo {
  return {
    count: 0,
    last_reason: null,
    last_at: null,
    ...overrides,
  };
}

describe("restartsSummary", () => {
  it("has a generic message when there's no restart data", () => {
    expect(restartsSummary(null)).toBe("container restarts across this app's pods");
  });

  it("has a generic message when the count is zero", () => {
    expect(restartsSummary(info({ count: 0 }))).toBe(
      "container restarts across this app's pods",
    );
  });

  it("includes a relative time and reason when both are known", () => {
    const now = new Date();
    const tenMinAgo = new Date(now.getTime() - 10 * 60 * 1000).toISOString();
    expect(restartsSummary(info({ count: 3, last_reason: "OOMKilled", last_at: tenMinAgo }))).toBe(
      "last 10 minutes ago · OOMKilled",
    );
  });

  it("omits the reason when it's unknown", () => {
    const now = new Date();
    const anHourAgo = new Date(now.getTime() - 60 * 60 * 1000).toISOString();
    expect(restartsSummary(info({ count: 1, last_reason: null, last_at: anHourAgo }))).toBe(
      "last 1 hour ago",
    );
  });

  it("falls back to 'unknown time' when last_at is missing", () => {
    expect(restartsSummary(info({ count: 2, last_reason: "Error", last_at: null }))).toBe(
      "last at an unknown time · Error",
    );
  });
});
