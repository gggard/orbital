import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import TokensPage from "./page";
import { makeMe, makeToken } from "@/test-utils/fixtures";
import type { Me, TokenOut } from "@/lib/types";

const mutate = vi.fn();
const revokeToken = vi.fn();
const createToken = vi.fn();
let tokensState: { data?: TokenOut[]; error?: Error; isLoading: boolean };
let me: Me | undefined;
vi.mock("@/lib/api", () => ({
  useTokens: () => ({ ...tokensState, mutate }),
  useMe: () => ({ data: me }),
  revokeToken: (...a: unknown[]) => revokeToken(...a),
  createToken: (...a: unknown[]) => createToken(...a),
}));

beforeEach(() => {
  mutate.mockReset();
  revokeToken.mockReset().mockResolvedValue({});
  createToken.mockReset().mockResolvedValue({ token: "orb_secret_123" });
  tokensState = { data: [], isLoading: false };
  me = makeMe();
});

describe("TokensPage list", () => {
  it("shows a skeleton while loading", () => {
    tokensState = { isLoading: true };
    const { container } = render(<TokensPage />);
    expect(container.querySelector(".MuiSkeleton-root")).toBeInTheDocument();
  });

  it("shows the empty state and the API error", () => {
    tokensState = { data: [], isLoading: false, error: new Error("boom") };
    render(<TokensPage />);
    expect(screen.getByText("No API tokens yet.")).toBeInTheDocument();
    expect(screen.getByText(/control plane unreachable: boom/)).toBeInTheDocument();
  });

  it("labels active, expired and revoked tokens", () => {
    tokensState = {
      isLoading: false,
      data: [
        makeToken({ id: "t1", name: "active-one", last_used_at: "2026-11-02T10:00:00Z" }),
        makeToken({ id: "t2", name: "old-one", expires_at: "2020-01-01T00:00:00Z" }),
        makeToken({ id: "t3", name: "gone-one", revoked_at: "2026-11-03T00:00:00Z" }),
      ],
    };
    render(<TokensPage />);
    const row = (name: string) => screen.getByText(name).closest("tr") as HTMLElement;
    expect(within(row("active-one")).getByText("active")).toBeInTheDocument();
    expect(within(row("old-one")).getByText("expired")).toBeInTheDocument();
    expect(within(row("old-one")).getByText("never")).toBeInTheDocument();
    expect(within(row("gone-one")).getByText("revoked")).toBeInTheDocument();
    expect(within(row("gone-one")).queryByRole("button")).not.toBeInTheDocument();
  });
});

describe("TokensPage revoke", () => {
  beforeEach(() => {
    tokensState = { isLoading: false, data: [makeToken({ name: "ci" })] };
  });

  it("revokes after confirmation and refreshes", async () => {
    render(<TokensPage />);
    fireEvent.click(within(screen.getByText("ci").closest("tr") as HTMLElement).getByRole("button"));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/Revoke "ci"\?/)).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Revoke" }));

    expect(await screen.findByText('Revoked "ci"')).toBeInTheDocument();
    expect(revokeToken).toHaveBeenCalledWith("t1");
    expect(mutate).toHaveBeenCalled();
  });

  it("reports revoke failures", async () => {
    revokeToken.mockRejectedValue(new Error("already revoked"));
    render(<TokensPage />);
    fireEvent.click(within(screen.getByText("ci").closest("tr") as HTMLElement).getByRole("button"));
    fireEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Revoke" }));
    expect(await screen.findByText("already revoked")).toBeInTheDocument();
    expect(mutate).not.toHaveBeenCalled();
  });
});

describe("CreateTokenDialog (via TokensPage)", () => {
  it("creates a token, shows it once, and resets on close", async () => {
    render(<TokensPage />);
    fireEvent.click(screen.getByRole("button", { name: /new token/i }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("leave blank to use the platform maximum of 90 days")).toBeInTheDocument();

    const create = within(dialog).getByRole("button", { name: "Create" });
    expect(create).toBeDisabled();
    fireEvent.change(within(dialog).getByLabelText(/name/i), { target: { value: " laptop " } });
    fireEvent.change(within(dialog).getByLabelText(/expires in/i), { target: { value: "30" } });
    fireEvent.click(create);

    expect(await screen.findByText("orb_secret_123")).toBeInTheDocument();
    expect(createToken).toHaveBeenCalledWith({ name: "laptop", ttl_days: 30 });
    expect(mutate).toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    fireEvent.click(await screen.findByRole("button", { name: /new token/i }));
    expect(await screen.findByText("New API token")).toBeInTheDocument();
    expect(screen.getByLabelText(/name/i)).toHaveValue("");
  });

  it("omits the TTL when blank and shows errors", async () => {
    createToken.mockRejectedValue(new Error("ttl too long"));
    me = undefined;
    tokensState = { data: [], isLoading: false };
    render(<TokensPage />);
    fireEvent.click(screen.getByRole("button", { name: /create your first token/i }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/platform's default \(and maximum\) TTL/)).toBeInTheDocument();

    fireEvent.change(within(dialog).getByLabelText(/name/i), { target: { value: "ci" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Create" }));
    expect(await within(dialog).findByText("ttl too long")).toBeInTheDocument();
    expect(createToken).toHaveBeenCalledWith({ name: "ci", ttl_days: undefined });

    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
  });
});
