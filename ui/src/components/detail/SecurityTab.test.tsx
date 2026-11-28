import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import SecurityTab from "./SecurityTab";
import { makeScan, makeVuln } from "@/test-utils/fixtures";
import type { ScanOut } from "@/lib/types";

let scans: ScanOut[] | undefined;
const useScanVulnerabilities = vi.fn();
vi.mock("@/lib/api", () => ({
  useAppScans: () => ({ data: scans }),
  useScanVulnerabilities: (appId: string, scanId: string | null) => useScanVulnerabilities(appId, scanId),
}));

beforeEach(() => {
  scans = undefined;
  useScanVulnerabilities.mockReset().mockImplementation((_a: string, id: string | null) => ({
    data: id ? [makeVuln()] : undefined,
  }));
});

describe("SecurityTab", () => {
  it("shows an empty state", () => {
    render(<SecurityTab appId="a1" />);
    expect(screen.getByText("no scans yet")).toBeInTheDocument();
  });

  it("lists scans and opens a scan's findings on click", async () => {
    scans = [makeScan({ id: "s1" }), makeScan({ id: "s2", status: "running", finished_at: null })];
    render(<SecurityTab appId="a1" />);
    expect(screen.getAllByText("b1")).toHaveLength(2);
    expect(screen.getByText("—")).toBeInTheDocument();

    fireEvent.click(screen.getByText("s1"));
    expect(await screen.findByText("scan s1")).toBeInTheDocument();
    expect(screen.getByText("CVE-2026-0001")).toBeInTheDocument();
    expect(useScanVulnerabilities).toHaveBeenLastCalledWith("a1", "s1");

    fireEvent.click(screen.getByText("s1"));
    expect(useScanVulnerabilities).toHaveBeenLastCalledWith("a1", null);
  });
});
