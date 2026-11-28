import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import AppDetail from "./page";
import { makeApp, makeMe, makeScan } from "@/test-utils/fixtures";
import type { AppOut, Me } from "@/lib/types";

vi.mock("next/navigation", () => ({ useParams: () => ({ id: "a1" }) }));

// each tab has its own tests; stubs keep this one about the page shell
vi.mock("@/components/detail/OverviewTab", () => ({ default: () => <div>overview-tab</div> }));
vi.mock("@/components/detail/MetricsTab", () => ({ default: () => <div>metrics-tab</div> }));
vi.mock("@/components/detail/AnalyticsTab", () => ({ default: () => <div>analytics-tab</div> }));
vi.mock("@/components/detail/LogsTab", () => ({ default: () => <div>logs-tab</div> }));
vi.mock("@/components/detail/BuildsTab", () => ({ default: () => <div>builds-tab</div> }));
vi.mock("@/components/detail/SecurityTab", () => ({ default: () => <div>security-tab</div> }));
vi.mock("@/components/detail/SecretsTab", () => ({
  default: ({ onSaved }: { onSaved: () => void }) => <button onClick={onSaved}>secrets-tab</button>,
}));
vi.mock("@/components/detail/SharingTab", () => ({
  default: ({ onSaved }: { onSaved: () => void }) => <button onClick={onSaved}>sharing-tab</button>,
}));
vi.mock("@/components/detail/SettingsTab", () => ({
  default: ({ onSaved }: { onSaved: (m: string) => void }) => (
    <button onClick={() => onSaved("settings saved")}>settings-tab</button>
  ),
}));

const mutate = vi.fn();
const deployApp = vi.fn();
const rebootApp = vi.fn();
const requestScan = vi.fn();
const wakeApp = vi.fn();
let appState: { data?: AppOut; error?: Error; isLoading: boolean };
let me: Me | undefined;
vi.mock("@/lib/api", () => ({
  useApp: () => ({ ...appState, mutate }),
  useMe: () => ({ data: me }),
  deployApp: (...a: unknown[]) => deployApp(...a),
  rebootApp: (...a: unknown[]) => rebootApp(...a),
  requestScan: (...a: unknown[]) => requestScan(...a),
  wakeApp: (...a: unknown[]) => wakeApp(...a),
}));

const button = (name: RegExp) => screen.getByRole("button", { name });

beforeEach(() => {
  for (const fn of [mutate, deployApp, rebootApp, requestScan, wakeApp]) fn.mockReset().mockResolvedValue({});
  appState = { data: makeApp(), isLoading: false };
  me = makeMe();
});

describe("AppDetail states", () => {
  it("shows a skeleton while loading", () => {
    appState = { isLoading: true };
    const { container } = render(<AppDetail />);
    expect(container.querySelector(".MuiSkeleton-root")).toBeInTheDocument();
  });

  it("shows not-found errors with a way back", () => {
    appState = { isLoading: false, error: new Error("404") };
    render(<AppDetail />);
    expect(screen.getByText("app not found (404)")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /back to apps/i })).toHaveAttribute("href", "/");
  });

  it("shows the header, access chip, URL and app error", () => {
    appState = { isLoading: false, data: makeApp({ allowed_groups: ["team", "ops"], error: "build failed: oops" }) };
    render(<AppDetail />);
    expect(screen.getByRole("heading", { name: "my-app" })).toBeInTheDocument();
    expect(screen.getByText("team, ops")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "https://my-app.example.com" })).toBeInTheDocument();
    expect(screen.getByText("build failed: oops")).toBeInTheDocument();
    expect(screen.getByText("overview-tab")).toBeInTheDocument();
  });

  it("labels private apps without groups and hides the chip for public ones", () => {
    const { rerender } = render(<AppDetail />);
    expect(screen.getByText("signed-in users")).toBeInTheDocument();
    appState = { isLoading: false, data: makeApp({ public: true }) };
    rerender(<AppDetail />);
    expect(screen.queryByText("signed-in users")).not.toBeInTheDocument();
  });
});

describe("AppDetail actions", () => {
  it("redeploys, reboots and rescans, refreshing after each", async () => {
    appState = { isLoading: false, data: makeApp({ current_build_id: "b1", latest_scan: makeScan() }) };
    render(<AppDetail />);
    expect(screen.queryByRole("button", { name: /wake now/i })).not.toBeInTheDocument();

    fireEvent.click(button(/redeploy/i));
    expect(await screen.findByText("redeploy scheduled")).toBeInTheDocument();
    fireEvent.click(button(/reboot/i));
    expect(await screen.findByText("reboot scheduled")).toBeInTheDocument();
    fireEvent.click(button(/rescan/i));
    expect(await screen.findByText("scan scheduled")).toBeInTheDocument();

    expect(deployApp).toHaveBeenCalledWith("a1");
    expect(rebootApp).toHaveBeenCalledWith("a1");
    expect(requestScan).toHaveBeenCalledWith("a1");
    expect(mutate).toHaveBeenCalledTimes(3);
  });

  it("wakes a sleeping app", async () => {
    appState = { isLoading: false, data: makeApp({ state: "sleeping" }) };
    render(<AppDetail />);
    expect(screen.getByRole("link", { name: /^open$/i })).toHaveAttribute("href", "https://my-app.example.com");
    expect(button(/reboot/i)).toBeDisabled();
    fireEvent.click(button(/wake now/i));
    expect(await screen.findByText("waking up")).toBeInTheDocument();
    expect(wakeApp).toHaveBeenCalledWith("a1");
  });

  it("disables actions that don't apply and reports failures", async () => {
    deployApp.mockRejectedValue(new Error("already building"));
    appState = {
      isLoading: false,
      data: makeApp({ state: "building", current_build_id: "b1", latest_scan: makeScan({ status: "running" }) }),
    };
    render(<AppDetail />);
    expect(button(/rescan/i)).toBeDisabled();
    expect(button(/reboot/i)).toBeDisabled();

    fireEvent.click(button(/redeploy/i));
    expect(await screen.findByText("already building")).toBeInTheDocument();
    expect(mutate).not.toHaveBeenCalled();
  });

  it("can't rescan before the first build", () => {
    render(<AppDetail />);
    expect(button(/rescan/i)).toBeDisabled();
  });
});

describe("AppDetail tabs", () => {
  it("switches between tabs", () => {
    render(<AppDetail />);
    for (const [tab, content] of [
      ["Metrics", "metrics-tab"],
      ["Analytics", "analytics-tab"],
      ["Logs", "logs-tab"],
      ["Builds", "builds-tab"],
      ["Security", "security-tab"],
      ["Overview", "overview-tab"],
    ]) {
      fireEvent.click(screen.getByRole("tab", { name: tab }));
      expect(screen.getByText(content)).toBeInTheDocument();
    }
  });

  it.each([
    ["Secrets", /secrets-tab/, "secrets saved — app restarting", 0],
    ["Sharing", /sharing-tab/, "sharing updated", 1],
    ["Settings", /settings-tab/, "settings saved", 1],
  ])("%s tab saves show a snackbar", async (tab, stub, message, refreshes) => {
    render(<AppDetail />);
    fireEvent.click(screen.getByRole("tab", { name: tab }));
    fireEvent.click(button(stub));
    expect(await screen.findByText(message)).toBeInTheDocument();
    expect(mutate).toHaveBeenCalledTimes(refreshes);
  });

  it("gives viewers a read-only page", () => {
    me = makeMe({ role: "viewer" });
    render(<AppDetail />);
    expect(screen.getAllByRole("tab").map((t) => t.textContent)).toEqual([
      "Overview",
      "Metrics",
      "Analytics",
      "Logs",
      "Builds",
      "Security",
    ]);
    expect(screen.queryByRole("button", { name: /redeploy/i })).not.toBeInTheDocument();
  });

  it("hides the Secrets tab for static sites", () => {
    appState = { isLoading: false, data: makeApp({ app_type: "static" }) };
    render(<AppDetail />);
    expect(screen.queryByRole("tab", { name: "Secrets" })).not.toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Settings" })).toBeInTheDocument();
  });
});
