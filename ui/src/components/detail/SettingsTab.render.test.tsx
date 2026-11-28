import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import SettingsTab from "./SettingsTab";
import { makeApp, makeMe } from "@/test-utils/fixtures";
import { addChip, removeChip } from "@/test-utils/pickers";
import type { Me } from "@/lib/types";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const patchApp = vi.fn();
const deleteApp = vi.fn();
let me: Me | undefined;
vi.mock("@/lib/api", () => ({
  useMe: () => ({ data: me }),
  useTags: () => ({ data: { tags: ["prod", "beta"] }, isLoading: false }),
  patchApp: (...a: unknown[]) => patchApp(...a),
  deleteApp: (...a: unknown[]) => deleteApp(...a),
}));

// Save buttons in render order: tags, source, polling, hibernation
const saveButton = (i: number) => screen.getAllByRole("button", { name: /^save$/i })[i];
const switches = () => screen.getAllByRole("switch");

beforeEach(() => {
  patchApp.mockReset().mockResolvedValue({});
  deleteApp.mockReset().mockResolvedValue({});
  push.mockReset();
  me = makeMe();
});

describe("SettingsTab source", () => {
  it("saves streamlit source fields and reports success", async () => {
    const onSaved = vi.fn();
    render(<SettingsTab app={makeApp()} onSaved={onSaved} />);
    expect(saveButton(1)).toBeDisabled();

    fireEvent.change(screen.getByLabelText("Branch"), { target: { value: "dev" } });
    fireEvent.change(screen.getByLabelText("Main file"), { target: { value: "main.py" } });
    expect(screen.getByText(/saving triggers a rebuild/i)).toBeInTheDocument();
    fireEvent.click(saveButton(1));

    await vi.waitFor(() => expect(onSaved).toHaveBeenCalledWith("settings saved — rebuild scheduled"));
    expect(patchApp).toHaveBeenCalledWith("a1", {
      branch: "dev",
      main_file: "main.py",
      python_version: "3.12",
    });
  });

  it("saves static source fields, omitting an empty build command", async () => {
    render(
      <SettingsTab app={makeApp({ app_type: "static", main_file: null, python_version: null })} onSaved={vi.fn()} />,
    );
    expect(screen.queryByLabelText("Main file")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Output directory"), { target: { value: "build" } });
    fireEvent.click(saveButton(1));
    await vi.waitFor(() =>
      expect(patchApp).toHaveBeenCalledWith("a1", {
        branch: "main",
        build_command: undefined,
        output_dir: "build",
      }),
    );

    fireEvent.change(screen.getByLabelText("Build command (optional)"), { target: { value: "npm run build" } });
    fireEvent.click(saveButton(1));
    await vi.waitFor(() =>
      expect(patchApp).toHaveBeenLastCalledWith("a1", {
        branch: "main",
        build_command: "npm run build",
        output_dir: "build",
      }),
    );
  });

  it("shows the error when saving fails", async () => {
    patchApp.mockRejectedValue(new Error("branch not found"));
    render(<SettingsTab app={makeApp()} onSaved={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Branch"), { target: { value: "nope" } });
    fireEvent.click(saveButton(1));
    expect(await screen.findByText("branch not found")).toBeInTheDocument();
  });

  it("shows the full webhook URL", () => {
    render(<SettingsTab app={makeApp()} onSaved={vi.fn()} />);
    expect(screen.getByText(`${window.location.origin}/webhooks/a1/token`)).toBeInTheDocument();
  });
});

describe("SettingsTab tags", () => {
  it("adds a tag and saves", async () => {
    const onSaved = vi.fn();
    render(<SettingsTab app={makeApp()} onSaved={onSaved} />);
    expect(saveButton(0)).toBeDisabled();

    addChip("Tags", "internal");
    fireEvent.click(saveButton(0));

    await vi.waitFor(() => expect(onSaved).toHaveBeenCalledWith("tags saved"));
    expect(patchApp).toHaveBeenCalledWith("a1", { tags: ["internal"] });
  });

  it("shows the error when saving tags fails", async () => {
    patchApp.mockRejectedValue("forbidden");
    render(<SettingsTab app={makeApp({ tags: ["prod"] })} onSaved={vi.fn()} />);
    removeChip("prod");
    fireEvent.click(saveButton(0));
    expect(await screen.findByText("forbidden")).toBeInTheDocument();
  });
});

describe("SettingsTab polling", () => {
  it("shows platform hints, rejects intervals below the minimum and saves a valid one", async () => {
    const onSaved = vi.fn();
    render(<SettingsTab app={makeApp()} onSaved={onSaved} />);
    fireEvent.click(switches()[0]);

    const field = screen.getByLabelText("Check interval (minutes)");
    expect(field).toHaveAttribute("placeholder", "10");
    expect(screen.getByText("platform default: 10 min · minimum: 5 min")).toBeInTheDocument();

    fireEvent.change(field, { target: { value: "2" } });
    expect(screen.getByText("must be at least 5 min (platform minimum)")).toBeInTheDocument();
    expect(saveButton(2)).toBeDisabled();

    fireEvent.change(field, { target: { value: "15" } });
    fireEvent.click(saveButton(2));
    await vi.waitFor(() => expect(onSaved).toHaveBeenCalledWith("auto-update settings saved"));
    expect(patchApp).toHaveBeenCalledWith("a1", { poll_enabled: true, poll_interval_seconds: 900 });
  });

  it("disables polling without an interval and surfaces errors", async () => {
    patchApp.mockRejectedValue(new Error("poll failed"));
    render(<SettingsTab app={makeApp({ poll_enabled: true, poll_interval_seconds: 600 })} onSaved={vi.fn()} />);
    expect(screen.getByLabelText("Check interval (minutes)")).toHaveValue(10);
    fireEvent.click(switches()[0]);
    fireEvent.click(saveButton(2));
    expect(await screen.findByText("poll failed")).toBeInTheDocument();
    expect(patchApp).toHaveBeenCalledWith("a1", { poll_enabled: false, poll_interval_seconds: 600 });
  });
});

describe("SettingsTab hibernation", () => {
  it("rejects timeouts above the maximum and saves a valid one", async () => {
    const onSaved = vi.fn();
    render(<SettingsTab app={makeApp()} onSaved={onSaved} />);
    fireEvent.click(switches()[1]);

    const field = screen.getByLabelText("Idle timeout (hours)");
    expect(field).toHaveAttribute("placeholder", "2");
    expect(screen.getByText("platform default: 2h · maximum: 24h")).toBeInTheDocument();

    fireEvent.change(field, { target: { value: "48" } });
    expect(screen.getByText("must be at most 24h (platform maximum)")).toBeInTheDocument();
    expect(saveButton(3)).toBeDisabled();

    fireEvent.change(field, { target: { value: "1.5" } });
    fireEvent.click(saveButton(3));
    await vi.waitFor(() => expect(onSaved).toHaveBeenCalledWith("hibernation settings saved"));
    expect(patchApp).toHaveBeenCalledWith("a1", { hibernate_enabled: true, hibernate_after_seconds: 5400 });
  });

  it("surfaces hibernation save errors", async () => {
    patchApp.mockRejectedValue(new Error("hibernate failed"));
    render(<SettingsTab app={makeApp()} onSaved={vi.fn()} />);
    fireEvent.click(switches()[1]);
    fireEvent.click(saveButton(3));
    expect(await screen.findByText("hibernate failed")).toBeInTheDocument();
    expect(patchApp).toHaveBeenCalledWith("a1", { hibernate_enabled: true });
  });

  it("falls back to generic hints before the platform limits are known", () => {
    me = undefined;
    render(<SettingsTab app={makeApp({ hibernate_enabled: true, poll_enabled: true })} onSaved={vi.fn()} />);
    expect(screen.getByLabelText("Idle timeout (hours)")).toHaveAttribute("placeholder", "platform default");
    expect(screen.getAllByText("leave blank to use the platform default")).toHaveLength(2);
  });
});

describe("SettingsTab danger zone", () => {
  it("deletes the app after typing its slug, then goes home", async () => {
    render(<SettingsTab app={makeApp()} onSaved={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /delete this app/i }));

    const dialog = await screen.findByRole("dialog");
    const confirm = within(dialog).getByRole("button", { name: /delete forever/i });
    expect(confirm).toBeDisabled();
    fireEvent.change(within(dialog).getByPlaceholderText("my-app"), { target: { value: "my-app" } });
    fireEvent.click(confirm);

    await vi.waitFor(() => expect(push).toHaveBeenCalledWith("/"));
    expect(deleteApp).toHaveBeenCalledWith("a1");
  });

  it("cancelling the dialog doesn't delete", async () => {
    render(<SettingsTab app={makeApp()} onSaved={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /delete this app/i }));
    fireEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: /cancel/i }));
    expect(deleteApp).not.toHaveBeenCalled();
  });
});
