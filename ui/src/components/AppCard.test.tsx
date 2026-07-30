import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { AdminAppOut } from "@/lib/types";
import AppCard from "./AppCard";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

const mockDeleteApp = vi.fn();
const mockDeployApp = vi.fn();
const mockRebootApp = vi.fn();
vi.mock("@/lib/api", () => ({
  deleteApp: (id: string) => mockDeleteApp(id),
  deployApp: (id: string) => mockDeployApp(id),
  rebootApp: (id: string) => mockRebootApp(id),
}));

function app(overrides: Partial<AdminAppOut> = {}): AdminAppOut {
  return {
    id: "app1",
    slug: "my-app",
    repo_url: "https://github.com/x/y",
    branch: "main",
    app_type: "streamlit",
    main_file: "app.py",
    python_version: "3.12",
    build_command: null,
    output_dir: "dist",
    public: true,
    allowed_groups: [],
    owner_groups: ["team-a"],
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
    updated_at: new Date().toISOString(),
    cpu: null,
    mem: null,
    restarts: null,
    cpu_series: [],
    mem_series: [],
    ...overrides,
  } as AdminAppOut;
}

describe("AppCard", () => {
  it("navigates to the app detail page when clicked", () => {
    render(<AppCard app={app()} readOnly={false} onAction={vi.fn()} />);
    fireEvent.click(screen.getByText("my-app"));
    expect(push).toHaveBeenCalledWith("/apps/app1");
  });

  it("renders a chip for every tag", () => {
    render(<AppCard app={app({ tags: ["prod", "critical"] })} readOnly={false} onAction={vi.fn()} />);
    expect(screen.getByText("prod")).toBeInTheDocument();
    expect(screen.getByText("critical")).toBeInTheDocument();
  });

  it("shows a lock icon and restricted-groups tooltip for private apps", () => {
    render(
      <AppCard
        app={app({ public: false, allowed_groups: ["ops"] })}
        readOnly={false}
        onAction={vi.fn()}
      />,
    );
    expect(document.querySelector('[data-testid="LockOutlinedIcon"]')).toBeInTheDocument();
  });

  it("redeploys and reports the result via onAction", async () => {
    mockDeployApp.mockResolvedValue(undefined);
    const onAction = vi.fn();
    render(<AppCard app={app()} readOnly={false} onAction={onAction} />);
    fireEvent.click(screen.getByLabelText("Redeploy (rebuild from git)"));
    await waitFor(() => expect(mockDeployApp).toHaveBeenCalledWith("app1"));
    await waitFor(() => expect(onAction).toHaveBeenCalledWith("redeploying my-app"));
  });

  it("reports the error message when redeploy fails", async () => {
    mockDeployApp.mockRejectedValue(new Error("network down"));
    const onAction = vi.fn();
    render(<AppCard app={app()} readOnly={false} onAction={onAction} />);
    fireEvent.click(screen.getByLabelText("Redeploy (rebuild from git)"));
    await waitFor(() => expect(onAction).toHaveBeenCalledWith("network down"));
  });

  const openOverflowMenu = () => {
    fireEvent.click(screen.getByTestId("MoreVertIcon").closest("button")!);
  };

  it("reboots from the overflow menu", async () => {
    mockRebootApp.mockResolvedValue(undefined);
    const onAction = vi.fn();
    render(<AppCard app={app()} readOnly={false} onAction={onAction} />);
    openOverflowMenu();
    fireEvent.click(await screen.findByText("Reboot"));
    await waitFor(() => expect(mockRebootApp).toHaveBeenCalledWith("app1"));
    await waitFor(() => expect(onAction).toHaveBeenCalledWith("rebooting my-app"));
  });

  it("deletes only after the confirm dialog is accepted", async () => {
    mockDeleteApp.mockResolvedValue(undefined);
    const onAction = vi.fn();
    render(<AppCard app={app()} readOnly={false} onAction={onAction} />);
    openOverflowMenu();
    fireEvent.click(await screen.findByText("Delete…"));
    expect(screen.getByText("Delete my-app?")).toBeInTheDocument();
    expect(mockDeleteApp).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(mockDeleteApp).toHaveBeenCalledWith("app1"));
    await waitFor(() => expect(onAction).toHaveBeenCalledWith("deleting my-app"));
  });

  it("hides mutating controls in read-only mode", () => {
    render(<AppCard app={app()} readOnly onAction={vi.fn()} />);
    expect(screen.queryByLabelText("Redeploy (rebuild from git)")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("more")).not.toBeInTheDocument();
  });

  it("shows a restart badge with correct singular/plural wording", () => {
    const { rerender } = render(
      <AppCard app={app({ restarts: 1 })} readOnly={false} onAction={vi.fn()} />,
    );
    expect(screen.getByText("⟳ 1 restart")).toBeInTheDocument();

    rerender(<AppCard app={app({ restarts: 3 })} readOnly={false} onAction={vi.fn()} />);
    expect(screen.getByText("⟳ 3 restarts")).toBeInTheDocument();
  });

  it("shows the app's error line when set", () => {
    render(<AppCard app={app({ error: "crash looping" })} readOnly={false} onAction={vi.fn()} />);
    expect(screen.getByText("crash looping")).toBeInTheDocument();
  });

  it("disables the open-app link unless the app is running or sleeping", () => {
    render(<AppCard app={app({ state: "build_failed" })} readOnly={false} onAction={vi.fn()} />);
    expect(screen.getByTestId("LaunchIcon").closest("a, button")).toHaveAttribute(
      "aria-disabled",
      "true",
    );
  });
});
