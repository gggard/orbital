import { describe, expect, it } from "vitest";
import { fmtAgo, fmtCpu, fmtMem } from "./format";

describe("fmtCpu", () => {
  it("formats sub-core values in millicores", () => {
    expect(fmtCpu(0.5)).toBe("500m");
    expect(fmtCpu(0.001)).toBe("1m");
  });

  it("formats values at or above one core with two decimals under 10", () => {
    expect(fmtCpu(1)).toBe("1.00");
    expect(fmtCpu(9.999)).toBe("10.00");
  });

  it("formats values at or above 10 cores with one decimal", () => {
    expect(fmtCpu(12.34)).toBe("12.3");
  });
});

describe("fmtMem", () => {
  it("formats sub-GiB values in MiB", () => {
    expect(fmtMem(1024 * 1024)).toBe("1 MiB");
    expect(fmtMem(512 * 1024 * 1024)).toBe("512 MiB");
  });

  it("formats GiB-and-above values in GiB with two decimals", () => {
    expect(fmtMem(2 * 1024 ** 3)).toBe("2.00 GiB");
    expect(fmtMem(1.5 * 1024 ** 3)).toBe("1.50 GiB");
  });
});

describe("fmtAgo", () => {
  const now = new Date("2026-01-02T12:00:00Z");

  it("says 'just now' for anything under a minute", () => {
    expect(fmtAgo("2026-01-02T11:59:30Z", now)).toBe("just now");
    expect(fmtAgo(now.toISOString(), now)).toBe("just now");
  });

  it("formats minutes", () => {
    expect(fmtAgo("2026-01-02T11:48:00Z", now)).toBe("12 minutes ago");
    expect(fmtAgo("2026-01-02T11:59:00Z", now)).toBe("1 minute ago");
  });

  it("formats hours", () => {
    expect(fmtAgo("2026-01-02T09:00:00Z", now)).toBe("3 hours ago");
    expect(fmtAgo("2026-01-02T11:00:00Z", now)).toBe("1 hour ago");
  });

  it("formats days", () => {
    expect(fmtAgo("2025-12-30T12:00:00Z", now)).toBe("3 days ago");
  });

  it("formats months", () => {
    expect(fmtAgo("2025-10-04T12:00:00Z", now)).toBe("3 months ago");
  });

  it("formats years", () => {
    expect(fmtAgo("2023-01-02T12:00:00Z", now)).toBe("3 years ago");
  });
});
