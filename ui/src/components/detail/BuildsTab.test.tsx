import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import BuildsTab from "./BuildsTab";
import { makeBuild } from "@/test-utils/fixtures";
import type { BuildOut } from "@/lib/types";

let builds: BuildOut[] | undefined;
const useBuildLogs = vi.fn();
vi.mock("@/lib/api", () => ({
  useBuilds: () => ({ data: builds }),
  useBuildLogs: (appId: string, buildId: string | null) => useBuildLogs(appId, buildId),
}));

beforeEach(() => {
  builds = undefined;
  useBuildLogs.mockReset().mockImplementation((_a: string, id: string | null) => ({
    data: id === "b2" ? "step 1\nstep 2" : undefined,
  }));
});

describe("BuildsTab", () => {
  it("shows an empty state", () => {
    render(<BuildsTab appId="a1" />);
    expect(screen.getByText("no builds yet")).toBeInTheDocument();
  });

  it("lists builds newest first with commit and duration", () => {
    builds = [
      makeBuild({ id: "b1", finished_at: "2026-11-01T10:00:45Z" }),
      makeBuild({ id: "b2", commit_sha: null, created_at: "2026-11-02T10:00:00Z", finished_at: "2026-11-02T10:03:30Z" }),
      makeBuild({ id: "b3", phase: "running", created_at: "2026-11-03T10:00:00Z", finished_at: null }),
    ];
    render(<BuildsTab appId="a1" />);
    const rows = screen.getAllByRole("row").slice(1);
    expect(rows.map((r) => within(r).getAllByRole("cell")[0].textContent)).toEqual(["b3", "b2", "b1"]);
    expect(within(rows[2]).getByText("abcdef1234")).toBeInTheDocument();
    expect(within(rows[2]).getByText("45s")).toBeInTheDocument();
    expect(within(rows[1]).getAllByText("—")).toHaveLength(1);
    expect(within(rows[1]).getByText("4m 30s")).toBeInTheDocument();
    expect(within(rows[0]).getByText("—")).toBeInTheDocument();
  });

  it("toggles a build's logs when its row is clicked", async () => {
    builds = [makeBuild({ id: "b1" }), makeBuild({ id: "b2" })];
    render(<BuildsTab appId="a1" />);

    fireEvent.click(screen.getByText("b2"));
    expect(await screen.findByText("build b2")).toBeInTheDocument();
    expect(screen.getByText(/step 1/)).toBeInTheDocument();
    expect(useBuildLogs).toHaveBeenLastCalledWith("a1", "b2");

    fireEvent.click(screen.getByText("b1"));
    expect(await screen.findByText("loading…")).toBeInTheDocument();

    fireEvent.click(screen.getByText("b1"));
    expect(useBuildLogs).toHaveBeenLastCalledWith("a1", null);
  });
});
