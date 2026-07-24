import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import AppsFilterBar, { EMPTY_FILTER } from "./AppsFilterBar";
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

describe("AppsFilterBar", () => {
  it("derives sorted, de-duplicated options from the given apps", () => {
    const apps = [
      app({ id: "1", state: "sleeping", owner_groups: ["team-b"], tags: ["dev"] }),
      app({ id: "2", state: "running", owner_groups: ["team-a", "team-b"], tags: ["prod", "dev"] }),
    ];
    render(<AppsFilterBar apps={apps} filter={EMPTY_FILTER} onChange={vi.fn()} />);

    expect(screen.getByPlaceholderText("Search by name…")).toBeInTheDocument();
    expect(screen.getByLabelText("State")).toBeInTheDocument();
    expect(screen.getByLabelText("Owner")).toBeInTheDocument();
    expect(screen.getByLabelText("Tags")).toBeInTheDocument();
  });

  it("renders with no apps at all", () => {
    render(<AppsFilterBar apps={[]} filter={EMPTY_FILTER} onChange={vi.fn()} />);
    expect(screen.getByPlaceholderText("Search by name…")).toBeInTheDocument();
  });
});
