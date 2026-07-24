import { describe, expect, it } from "vitest";
import { applyFilter, EMPTY_FILTER, filterCount, type AppsFilter } from "./AppsFilterBar";
import type { AdminAppOut } from "@/lib/types";

function app(overrides: Partial<AdminAppOut>): AdminAppOut {
  return {
    id: "1",
    slug: "my-app",
    state: "running",
    owner_groups: [],
    tags: [],
    cpu: null,
    mem: null,
    ...overrides,
  } as AdminAppOut;
}

describe("filterCount", () => {
  it("is 0 for the empty filter", () => {
    expect(filterCount(EMPTY_FILTER)).toBe(0);
  });

  it("counts search plus each list entry", () => {
    const filter: AppsFilter = {
      search: "x",
      states: ["running"],
      owners: ["team-a", "team-b"],
      tags: ["prod"],
    };
    expect(filterCount(filter)).toBe(5);
  });
});

describe("applyFilter", () => {
  const apps = [
    app({ id: "1", slug: "dashboard", state: "running", owner_groups: ["team-a"], tags: ["prod"] }),
    app({ id: "2", slug: "reports", state: "sleeping", owner_groups: ["team-b"], tags: ["dev"] }),
  ];

  it("returns all apps for the empty filter", () => {
    expect(applyFilter(apps, EMPTY_FILTER)).toHaveLength(2);
  });

  it("filters by case-insensitive slug search", () => {
    const result = applyFilter(apps, { ...EMPTY_FILTER, search: "DASH" });
    expect(result.map((a) => a.id)).toEqual(["1"]);
  });

  it("filters by state", () => {
    const result = applyFilter(apps, { ...EMPTY_FILTER, states: ["sleeping"] });
    expect(result.map((a) => a.id)).toEqual(["2"]);
  });

  it("filters by owner group", () => {
    const result = applyFilter(apps, { ...EMPTY_FILTER, owners: ["team-a"] });
    expect(result.map((a) => a.id)).toEqual(["1"]);
  });

  it("filters by tag", () => {
    const result = applyFilter(apps, { ...EMPTY_FILTER, tags: ["dev"] });
    expect(result.map((a) => a.id)).toEqual(["2"]);
  });

  it("combines filters with AND semantics", () => {
    const result = applyFilter(apps, { ...EMPTY_FILTER, search: "dash", tags: ["dev"] });
    expect(result).toHaveLength(0);
  });
});
