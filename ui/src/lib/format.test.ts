import { describe, expect, it } from "vitest";
import { fmtCpu, fmtMem } from "./format";

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
