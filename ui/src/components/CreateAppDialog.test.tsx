import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import CreateAppDialog from "./CreateAppDialog";
import { makeApp, makeMe } from "@/test-utils/fixtures";
import { addChip } from "@/test-utils/pickers";
import type { Me } from "@/lib/types";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const createApp = vi.fn();
let me: Me | undefined;
vi.mock("@/lib/api", () => ({
  useMe: () => ({ data: me }),
  useTags: () => ({ data: { tags: [] } }),
  useGroups: () => ({ data: { groups: ["team"] } }),
  createApp: (...a: unknown[]) => createApp(...a),
}));

const deploy = () => screen.getByRole("button", { name: /^deploy$/i });

function fillRequired(slug = "new-app") {
  fireEvent.change(screen.getByLabelText(/^slug/i), { target: { value: slug } });
  fireEvent.change(screen.getByLabelText(/git repository url/i), {
    target: { value: "  https://github.com/org/repo  " },
  });
}

beforeEach(() => {
  createApp.mockReset().mockResolvedValue(makeApp({ id: "new-id" }));
  push.mockReset();
  me = makeMe();
});

describe("CreateAppDialog", () => {
  it("validates the slug before enabling Deploy", () => {
    render(<CreateAppDialog open onClose={vi.fn()} />);
    expect(deploy()).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/^slug/i), { target: { value: "Bad_Slug" } });
    expect(screen.getByLabelText(/^slug/i)).toHaveValue("bad_slug");
    expect(screen.getByText(/lowercase letters, digits and dashes only/)).toBeInTheDocument();

    fillRequired();
    expect(deploy()).toBeEnabled();
  });

  it("creates a public streamlit app with secrets and opens it", async () => {
    const onClose = vi.fn();
    render(<CreateAppDialog open onClose={onClose} />);
    fillRequired();
    fireEvent.change(screen.getByLabelText("Branch"), { target: { value: "  " } });
    fireEvent.click(screen.getByText("Secrets (optional)"));
    fireEvent.change(screen.getByPlaceholderText(/api_key/), { target: { value: 'k = "v"\n' } });
    addChip("Tags", "demo");
    fireEvent.click(deploy());

    await vi.waitFor(() => expect(push).toHaveBeenCalledWith("/apps/new-id"));
    expect(onClose).toHaveBeenCalled();
    expect(createApp).toHaveBeenCalledWith({
      slug: "new-app",
      repo_url: "https://github.com/org/repo",
      branch: "main",
      app_type: "streamlit",
      main_file: "streamlit_app.py",
      python_version: "3.12",
      public: true,
      allowed_groups: [],
      tags: ["demo"],
      secrets_toml: 'k = "v"',
    });
  });

  it("creates a private static site restricted to groups", async () => {
    render(<CreateAppDialog open onClose={vi.fn()} />);
    fillRequired("site");

    fireEvent.mouseDown(screen.getByRole("combobox", { name: /app type/i }));
    fireEvent.click(within(screen.getByRole("listbox")).getByText("Static site"));
    expect(screen.queryByText("Secrets (optional)")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Output directory"), { target: { value: " " } });

    fireEvent.click(screen.getByRole("switch"));
    addChip("Allowed groups", "team");
    fireEvent.click(deploy());

    await vi.waitFor(() => expect(createApp).toHaveBeenCalled());
    expect(createApp.mock.calls[0][0]).toMatchObject({
      slug: "site",
      app_type: "static",
      build_command: undefined,
      output_dir: ".",
      public: false,
      allowed_groups: ["team"],
      secrets_toml: undefined,
    });
  });

  it("forces private apps when the platform restricts publishing", async () => {
    me = makeMe({ can_publish: false });
    render(<CreateAppDialog open onClose={vi.fn()} />);
    expect(screen.getByRole("switch")).toBeDisabled();
    expect(screen.getByText(/public sharing is restricted/i)).toBeInTheDocument();
    expect(screen.getByLabelText("Allowed groups")).toBeInTheDocument();

    fillRequired();
    fireEvent.click(deploy());
    await vi.waitFor(() => expect(createApp).toHaveBeenCalled());
    expect(createApp.mock.calls[0][0]).toMatchObject({ public: false, allowed_groups: [] });
  });

  it("shows the API error and stays open", async () => {
    createApp.mockRejectedValue(new Error("slug already taken"));
    const onClose = vi.fn();
    render(<CreateAppDialog open onClose={onClose} />);
    fillRequired();
    fireEvent.click(deploy());
    expect(await screen.findByText("slug already taken")).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
  });
});
