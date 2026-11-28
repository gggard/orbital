import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import SharingTab from "./SharingTab";
import { makeApp, makeMe } from "@/test-utils/fixtures";
import { addChip, removeChip } from "@/test-utils/pickers";
import type { Me } from "@/lib/types";

const patchApp = vi.fn();
let me: Me | undefined;
vi.mock("@/lib/api", () => ({
  useMe: () => ({ data: me }),
  useGroups: () => ({ data: { groups: ["team", "ops"] } }),
  patchApp: (...a: unknown[]) => patchApp(...a),
}));

const saveAccess = () => screen.getByRole("button", { name: /^save$/i });
const saveOwnership = () => screen.getByRole("button", { name: /save ownership/i });

beforeEach(() => {
  patchApp.mockReset().mockResolvedValue({});
  me = makeMe({ groups: ["team"] });
});

describe("SharingTab viewer access", () => {
  it("makes a public app private for specific groups", async () => {
    const onSaved = vi.fn();
    render(<SharingTab app={makeApp({ public: true, owner_groups: ["team"] })} onSaved={onSaved} />);
    expect(screen.getByText("Public — anyone with the URL")).toBeInTheDocument();
    expect(saveAccess()).toBeDisabled();

    fireEvent.click(screen.getByRole("switch"));
    expect(screen.getByText("Private — sign-in required")).toBeInTheDocument();
    addChip("Allowed viewer groups", "ops");
    fireEvent.click(saveAccess());

    await vi.waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(patchApp).toHaveBeenCalledWith("a1", { public: false, allowed_groups: ["ops"] });
  });

  it("clears allowed groups when making an app public", async () => {
    render(<SharingTab app={makeApp({ allowed_groups: ["ops"], owner_groups: ["team"] })} onSaved={vi.fn()} />);
    fireEvent.click(screen.getByRole("switch"));
    fireEvent.click(saveAccess());
    await vi.waitFor(() => expect(patchApp).toHaveBeenCalledWith("a1", { public: true, allowed_groups: [] }));
  });

  it("blocks publishing when the platform restricts it", () => {
    me = makeMe({ can_publish: false, groups: ["team"] });
    render(<SharingTab app={makeApp({ owner_groups: ["team"] })} onSaved={vi.fn()} />);
    expect(screen.getByRole("switch")).toBeDisabled();
    expect(screen.getByText(/public sharing is restricted/i)).toBeInTheDocument();
  });

  it("shows save errors", async () => {
    patchApp.mockRejectedValue(new Error("not allowed"));
    render(<SharingTab app={makeApp({ owner_groups: ["team"] })} onSaved={vi.fn()} />);
    fireEvent.click(screen.getByRole("switch"));
    fireEvent.click(saveAccess());
    expect(await screen.findByText("not allowed")).toBeInTheDocument();
  });
});

describe("SharingTab ownership", () => {
  it("stops non-admins from locking themselves out, then saves", async () => {
    const onSaved = vi.fn();
    render(<SharingTab app={makeApp({ owner_groups: ["team"] })} onSaved={onSaved} />);

    removeChip("team");
    expect(screen.getByText(/owner groups cannot be empty/i)).toBeInTheDocument();
    expect(saveOwnership()).toBeDisabled();

    addChip("Owner groups", "ops");
    expect(screen.getByText(/you must keep at least one of your own groups/i)).toBeInTheDocument();
    expect(saveOwnership()).toBeDisabled();

    addChip("Owner groups", "team");
    expect(saveOwnership()).toBeEnabled();
    fireEvent.click(saveOwnership());
    await vi.waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(patchApp).toHaveBeenCalledWith("a1", { owner_groups: ["ops", "team"] });
  });

  it("lets admins clear owners, with a warning", async () => {
    me = makeMe({ role: "admin", groups: [] });
    render(<SharingTab app={makeApp({ owner_groups: ["team"] })} onSaved={vi.fn()} />);
    removeChip("team");
    expect(screen.getByText(/only admins will see this app/i)).toBeInTheDocument();
    expect(saveOwnership()).toBeEnabled();
  });

  it("shows ownership save errors", async () => {
    patchApp.mockRejectedValue("conflict");
    render(<SharingTab app={makeApp({ owner_groups: ["team"] })} onSaved={vi.fn()} />);
    addChip("Owner groups", "ops");
    fireEvent.click(saveOwnership());
    expect(await screen.findByText("conflict")).toBeInTheDocument();
  });
});
