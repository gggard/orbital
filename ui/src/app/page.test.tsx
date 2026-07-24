import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { AppsListBody } from "./page";
import type { AdminAppOut } from "@/lib/types";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

function app(overrides: Partial<AdminAppOut>): AdminAppOut {
  return {
    id: "1",
    slug: "my-app",
    repo_url: "https://example.com/repo.git",
    branch: "main",
    app_type: "streamlit",
    main_file: "app.py",
    python_version: "3.12",
    build_command: null,
    output_dir: "dist",
    public: false,
    allowed_groups: [],
    owner_groups: [],
    tags: [],
    state: "running",
    error: null,
    current_build_id: null,
    latest_scan: null,
    url: "https://my-app.example.com",
    webhook_path: "/webhooks/1",
    hibernate_enabled: false,
    hibernate_after_seconds: null,
    poll_enabled: false,
    poll_interval_seconds: null,
    last_polled_at: null,
    last_active_at: "",
    created_at: "",
    updated_at: "",
    cpu: null,
    mem: null,
    ...overrides,
  };
}

const noop = () => {};

describe("AppsListBody", () => {
  it("shows skeletons while loading", () => {
    const { container } = render(
      <AppsListBody
        loading
        allApps={[]}
        filteredApps={[]}
        canCreate={false}
        view="cards"
        readOnly={false}
        onCreate={noop}
        onClearFilters={noop}
        onAction={noop}
      />,
    );
    expect(container.querySelectorAll(".MuiSkeleton-root")).toHaveLength(3);
  });

  it("invites creators to deploy their first app when there are none", () => {
    render(
      <AppsListBody
        loading={false}
        allApps={[]}
        filteredApps={[]}
        canCreate
        view="cards"
        readOnly={false}
        onCreate={noop}
        onClearFilters={noop}
        onAction={noop}
      />,
    );
    expect(screen.getByText(/deploy your first streamlit app/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /deploy your first app/i })).toBeInTheDocument();
  });

  it("tells viewers nothing is shared when there are no apps", () => {
    render(
      <AppsListBody
        loading={false}
        allApps={[]}
        filteredApps={[]}
        canCreate={false}
        view="cards"
        readOnly
        onCreate={noop}
        onClearFilters={noop}
        onAction={noop}
      />,
    );
    expect(screen.getByText(/no apps are shared with your groups/i)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("offers to clear filters when they exclude every app", () => {
    render(
      <AppsListBody
        loading={false}
        allApps={[app({})]}
        filteredApps={[]}
        canCreate={false}
        view="cards"
        readOnly={false}
        onCreate={noop}
        onClearFilters={noop}
        onAction={noop}
      />,
    );
    expect(screen.getByText("No apps match these filters.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Clear filters" })).toBeInTheDocument();
  });

  it("renders a table when the view is 'table'", () => {
    render(
      <AppsListBody
        loading={false}
        allApps={[app({})]}
        filteredApps={[app({ slug: "my-app" })]}
        canCreate={false}
        view="table"
        readOnly={false}
        onCreate={noop}
        onClearFilters={noop}
        onAction={noop}
      />,
    );
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByText("my-app")).toBeInTheDocument();
  });

  it("renders cards when the view is 'cards'", () => {
    render(
      <AppsListBody
        loading={false}
        allApps={[app({})]}
        filteredApps={[app({ slug: "my-app" })]}
        canCreate={false}
        view="cards"
        readOnly={false}
        onCreate={noop}
        onClearFilters={noop}
        onAction={noop}
      />,
    );
    expect(screen.getByText("my-app")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});
