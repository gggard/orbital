import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import AppsFilterBar, { EMPTY_FILTER } from "./AppsFilterBar";
import type { AdminAppOut } from "@/lib/types";

function app(overrides: Partial<AdminAppOut>): AdminAppOut {
  return {
    id: "1",
    slug: "my-app",
    repo_url: "https://example.com/team/my-app",
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

    expect(screen.getByPlaceholderText("Search by name or repo…")).toBeInTheDocument();
    expect(screen.getByLabelText("State")).toBeInTheDocument();
    expect(screen.getByLabelText("Owner")).toBeInTheDocument();
    expect(screen.getByText("dev")).toBeInTheDocument();
    expect(screen.getByText("prod")).toBeInTheDocument();
  });

  it("renders with no apps at all", () => {
    render(<AppsFilterBar apps={[]} filter={EMPTY_FILTER} onChange={vi.fn()} />);
    expect(screen.getByPlaceholderText("Search by name or repo…")).toBeInTheDocument();
  });

  it("toggles a tag pill on click", () => {
    const apps = [app({ id: "1", tags: ["prod"] })];
    const onChange = vi.fn();
    render(<AppsFilterBar apps={apps} filter={EMPTY_FILTER} onChange={onChange} />);

    fireEvent.click(screen.getByText("prod"));
    expect(onChange).toHaveBeenCalledWith({ ...EMPTY_FILTER, tags: ["prod"] });
  });

  it("shows an active tag pill as filled", () => {
    const apps = [app({ id: "1", tags: ["prod"] })];
    render(
      <AppsFilterBar apps={apps} filter={{ ...EMPTY_FILTER, tags: ["prod"] }} onChange={vi.fn()} />,
    );
    expect(screen.getByText("prod").closest(".MuiChip-root")).toHaveClass("MuiChip-filled");
  });
});
