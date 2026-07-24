import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import SeverityChip from "./SeverityChip";
import type { ScanOut } from "@/lib/types";

function scan(overrides: Partial<ScanOut>): ScanOut {
  return {
    id: "s1",
    app_id: "a1",
    build_id: null,
    image: "img",
    status: "succeeded",
    trivy_version: null,
    critical_count: 0,
    high_count: 0,
    medium_count: 0,
    low_count: 0,
    unknown_count: 0,
    error: null,
    created_at: "",
    finished_at: null,
    ...overrides,
  };
}

describe("SeverityChip", () => {
  it("shows 'not scanned' when there is no scan", () => {
    render(<SeverityChip scan={null} />);
    expect(screen.getByText("not scanned")).toBeInTheDocument();
  });

  it("shows a busy label while scanning", () => {
    render(<SeverityChip scan={scan({ status: "running" })} />);
    expect(screen.getByText("scanning…")).toBeInTheDocument();
  });

  it("shows 'scan failed' when the scan failed", () => {
    render(<SeverityChip scan={scan({ status: "failed" })} />);
    expect(screen.getByText("scan failed")).toBeInTheDocument();
  });

  it("prioritizes critical over lower severities", () => {
    render(<SeverityChip scan={scan({ critical_count: 2, high_count: 5 })} />);
    expect(screen.getByText("2 critical")).toBeInTheDocument();
  });

  it("falls back to 'clean' when nothing was found", () => {
    render(<SeverityChip scan={scan({})} />);
    expect(screen.getByText("clean")).toBeInTheDocument();
  });
});
