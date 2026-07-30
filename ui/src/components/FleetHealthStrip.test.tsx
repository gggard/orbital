import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { EMPTY_FILTER } from "@/components/AppsFilterBar";
import type { AdminAppOut, AppState } from "@/lib/types";
import FleetHealthStrip from "./FleetHealthStrip";

function app(state: AppState, overrides: Partial<AdminAppOut> = {}): AdminAppOut {
  return {
    id: state,
    slug: state,
    state,
    cpu: null,
    mem: null,
    restarts: null,
    cpu_series: [],
    mem_series: [],
    ...overrides,
  } as AdminAppOut;
}

const APPS: AdminAppOut[] = [
  app("running"),
  app("running", { id: "r2", slug: "r2" }),
  app("building"),
  app("build_failed"),
  app("sleeping"),
];

describe("FleetHealthStrip", () => {
  it("counts apps into their health category", () => {
    render(
      <FleetHealthStrip apps={APPS} totals={null} filter={EMPTY_FILTER} onChange={vi.fn()} />,
    );
    expect(screen.getByText("Running")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument(); // Running
    // "In progress" (building), "Failed" (build_failed), and "Sleeping" all count 1
    expect(screen.getAllByText("1")).toHaveLength(3);
  });

  it("shows totals as em-dash when not provided (non-admin)", () => {
    render(
      <FleetHealthStrip apps={APPS} totals={null} filter={EMPTY_FILTER} onChange={vi.fn()} />,
    );
    expect(screen.getAllByText("—")).toHaveLength(2);
  });

  it("formats cpu/mem totals when provided", () => {
    render(
      <FleetHealthStrip
        apps={APPS}
        totals={{ cpu: 0.5, mem: 512 * 2 ** 20 }}
        filter={EMPTY_FILTER}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByText("500m")).toBeInTheDocument();
    expect(screen.getByText("512 MiB")).toBeInTheDocument();
  });

  it("clicking a stat card sets the matching state filter", () => {
    const onChange = vi.fn();
    render(
      <FleetHealthStrip apps={APPS} totals={null} filter={EMPTY_FILTER} onChange={onChange} />,
    );
    fireEvent.click(screen.getByText("Running"));
    expect(onChange).toHaveBeenCalledWith({ ...EMPTY_FILTER, states: ["running"] });
  });

  it("clicking the active stat card clears the filter", () => {
    const onChange = vi.fn();
    render(
      <FleetHealthStrip
        apps={APPS}
        totals={null}
        filter={{ ...EMPTY_FILTER, states: ["running"] }}
        onChange={onChange}
      />,
    );
    fireEvent.click(screen.getByText("Running"));
    expect(onChange).toHaveBeenCalledWith({ ...EMPTY_FILTER, states: [] });
  });
});
