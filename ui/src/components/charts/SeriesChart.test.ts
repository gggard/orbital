import { describe, expect, it } from "vitest";
import { computeTimeTicks } from "./SeriesChart";

describe("computeTimeTicks", () => {
  it("returns a single tick for a single-point series", () => {
    expect(computeTimeTicks(0)).toEqual([0]);
  });

  it("returns start and end ticks for a multi-point series", () => {
    expect(computeTimeTicks(1)).toEqual([0, 1]);
    expect(computeTimeTicks(42)).toEqual([0, 42]);
  });
});
