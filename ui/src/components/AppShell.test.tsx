import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import type { Me } from "@/lib/types";
import AppShell from "./AppShell";

const mockUseMe = vi.fn();
const mockLogout = vi.fn();
vi.mock("@/lib/api", () => ({
  useMe: () => mockUseMe(),
  loginUrl: (next: string) => `/api/auth/login?next=${encodeURIComponent(next)}`,
  logout: () => mockLogout(),
}));

const mockSetMode = vi.fn();
const mockUseColorScheme = vi.fn(() => ({ mode: "light", setMode: mockSetMode }));
vi.mock("@mui/material/styles", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@mui/material/styles")>();
  return { ...actual, useColorScheme: () => mockUseColorScheme() };
});

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
}));

function me(overrides: Partial<Me> = {}): Me {
  return {
    authenticated: true,
    auth_enabled: true,
    email: "alice.smith@example.com",
    groups: ["admins"],
    role: "admin",
    can_create: true,
    can_publish: true,
    git_poll_default_interval_seconds: 60,
    git_poll_min_interval_seconds: 30,
    hibernation_timeout_seconds: 3600,
    hibernation_max_timeout_seconds: 86400,
    api_token_max_ttl_days: 30,
    ...overrides,
  };
}

describe("AppShell", () => {
  it("shows a skeleton instead of children while /me is loading", () => {
    mockUseMe.mockReturnValue({ data: undefined, error: undefined, isLoading: true });
    render(
      <AppShell>
        <div>secret content</div>
      </AppShell>,
    );
    expect(screen.queryByText("secret content")).not.toBeInTheDocument();
  });

  it("prompts sign-in on a 401 and never renders children", () => {
    mockUseMe.mockReturnValue({ data: undefined, error: { status: 401 }, isLoading: false });
    render(
      <AppShell>
        <div>secret content</div>
      </AppShell>,
    );
    expect(screen.getByRole("link", { name: /sign in/i })).toHaveAttribute(
      "href",
      "/api/auth/login?next=%2F",
    );
    expect(screen.queryByText("secret content")).not.toBeInTheDocument();
  });

  it("shows an unauthorized-groups warning on a 403 and offers a different login", () => {
    mockUseMe.mockReturnValue({ data: undefined, error: { status: 403 }, isLoading: false });
    render(
      <AppShell>
        <div>secret content</div>
      </AppShell>,
    );
    expect(screen.getByText(/none of your groups grant access/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /sign in as a different user/i }));
    expect(mockLogout).toHaveBeenCalled();
  });

  it("surfaces other errors as a control-plane-unreachable alert", () => {
    mockUseMe.mockReturnValue({
      data: undefined,
      error: { status: 500, message: "boom" },
      isLoading: false,
    });
    render(
      <AppShell>
        <div>secret content</div>
      </AppShell>,
    );
    expect(screen.getByText(/control plane unreachable: boom/i)).toBeInTheDocument();
  });

  it("renders children once authenticated", () => {
    mockUseMe.mockReturnValue({ data: me(), error: undefined, isLoading: false });
    render(
      <AppShell>
        <div>secret content</div>
      </AppShell>,
    );
    expect(screen.getByText("secret content")).toBeInTheDocument();
  });

  it("shows the admin link only for admins", () => {
    mockUseMe.mockReturnValue({ data: me({ role: "admin" }), error: undefined, isLoading: false });
    const { rerender } = render(
      <AppShell>
        <div />
      </AppShell>,
    );
    expect(screen.getByLabelText("admin dashboard")).toBeInTheDocument();

    mockUseMe.mockReturnValue({ data: me({ role: "viewer" }), error: undefined, isLoading: false });
    rerender(
      <AppShell>
        <div />
      </AppShell>,
    );
    expect(screen.queryByLabelText("admin dashboard")).not.toBeInTheDocument();
  });

  it("hides the user menu entirely when auth is disabled", () => {
    mockUseMe.mockReturnValue({
      data: me({ auth_enabled: false }),
      error: undefined,
      isLoading: false,
    });
    render(
      <AppShell>
        <div />
      </AppShell>,
    );
    expect(screen.queryByLabelText("account")).not.toBeInTheDocument();
  });

  it("shows initials from the two-part local part of the email", () => {
    mockUseMe.mockReturnValue({
      data: me({ email: "alice.smith@example.com" }),
      error: undefined,
      isLoading: false,
    });
    render(
      <AppShell>
        <div />
      </AppShell>,
    );
    expect(screen.getByText("AS")).toBeInTheDocument();
  });

  it("falls back to the first letter for a single-part local part", () => {
    mockUseMe.mockReturnValue({
      data: me({ email: "bob@example.com" }),
      error: undefined,
      isLoading: false,
    });
    render(
      <AppShell>
        <div />
      </AppShell>,
    );
    expect(screen.getByText("B")).toBeInTheDocument();
  });

  it("opens the account menu with the user's email, role and groups", () => {
    mockUseMe.mockReturnValue({
      data: me({ email: "carol@example.com", role: "creator", groups: ["team-a", "team-b"] }),
      error: undefined,
      isLoading: false,
    });
    render(
      <AppShell>
        <div />
      </AppShell>,
    );
    fireEvent.click(screen.getByLabelText("account"));
    expect(screen.getByText("carol@example.com")).toBeInTheDocument();
    expect(screen.getByText("creator · team-a, team-b")).toBeInTheDocument();
  });

  it("shows 'no groups' when the user belongs to none", () => {
    mockUseMe.mockReturnValue({
      data: me({ groups: [] }),
      error: undefined,
      isLoading: false,
    });
    render(
      <AppShell>
        <div />
      </AppShell>,
    );
    fireEvent.click(screen.getByLabelText("account"));
    expect(screen.getByText(/no groups/)).toBeInTheDocument();
  });

  it("signs out from the account menu", () => {
    mockUseMe.mockReturnValue({ data: me(), error: undefined, isLoading: false });
    render(
      <AppShell>
        <div />
      </AppShell>,
    );
    fireEvent.click(screen.getByLabelText("account"));
    fireEvent.click(screen.getByText("Sign out"));
    expect(mockLogout).toHaveBeenCalled();
  });

  it("links to the tokens page from the account menu", () => {
    mockUseMe.mockReturnValue({ data: me(), error: undefined, isLoading: false });
    render(
      <AppShell>
        <div />
      </AppShell>,
    );
    fireEvent.click(screen.getByLabelText("account"));
    expect(screen.getByRole("menuitem", { name: /my tokens/i })).toHaveAttribute(
      "href",
      "/tokens",
    );
  });

  it("toggles color scheme between light and dark", () => {
    mockUseMe.mockReturnValue({ data: me(), error: undefined, isLoading: false });
    mockUseColorScheme.mockReturnValue({ mode: "light", setMode: mockSetMode });
    render(
      <AppShell>
        <div />
      </AppShell>,
    );
    fireEvent.click(screen.getByLabelText("toggle color scheme"));
    expect(mockSetMode).toHaveBeenCalledWith("dark");
  });

  it("shows the light-mode icon and label when currently dark", () => {
    mockUseMe.mockReturnValue({ data: me(), error: undefined, isLoading: false });
    mockUseColorScheme.mockReturnValue({ mode: "dark", setMode: mockSetMode });
    render(
      <AppShell>
        <div />
      </AppShell>,
    );
    fireEvent.click(screen.getByLabelText("toggle color scheme"));
    expect(mockSetMode).toHaveBeenCalledWith("light");
  });
});
