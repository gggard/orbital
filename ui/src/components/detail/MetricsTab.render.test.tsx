import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import type { MetricsOut } from "@/lib/types";
import MetricsTab from "./MetricsTab";

const mockUseAppMetrics = vi.fn();
vi.mock("@/lib/api", () => ({
  useAppMetrics: (id: string) => mockUseAppMetrics(id),
}));

function metrics(overrides: Partial<MetricsOut>): MetricsOut {
  return {
    available: false,
    limits: { cpu: 1, mem: 2 * 1024 ** 3 },
    current: null,
    series: [],
    restarts: null,
    ...overrides,
  };
}

describe("MetricsTab", () => {
  it("shows a skeleton while loading", () => {
    mockUseAppMetrics.mockReturnValue({ data: undefined, error: undefined, isLoading: true });
    const { container } = render(<MetricsTab appId="a1" />);
    expect(container.querySelector(".MuiSkeleton-root")).toBeInTheDocument();
  });

  it("shows an error message on fetch failure", () => {
    mockUseAppMetrics.mockReturnValue({
      data: undefined,
      error: new Error("network down"),
      isLoading: false,
    });
    render(<MetricsTab appId="a1" />);
    expect(screen.getByText(/failed to load metrics: network down/i)).toBeInTheDocument();
  });

  it("shows the restarts stat and a 'no usage metrics' notice when there's no CPU/mem data yet", () => {
    mockUseAppMetrics.mockReturnValue({
      data: metrics({ restarts: { count: 4, last_reason: "OOMKilled", last_at: null } }),
      error: undefined,
      isLoading: false,
    });
    render(<MetricsTab appId="a1" />);
    expect(screen.getByText("4")).toBeInTheDocument();
    expect(screen.getByText(/no usage metrics yet/i)).toBeInTheDocument();
  });

  it("renders CPU/memory charts and the restarts stat once usage data is available", () => {
    mockUseAppMetrics.mockReturnValue({
      data: metrics({
        available: true,
        current: { t: 1, cpu: 0.5, mem: 1024 ** 3 },
        series: [{ t: 1, cpu: 0.5, mem: 1024 ** 3 }],
        restarts: { count: 0, last_reason: null, last_at: null },
      }),
      error: undefined,
      isLoading: false,
    });
    render(<MetricsTab appId="a1" />);
    expect(screen.getByText("CPU")).toBeInTheDocument();
    expect(screen.getByText("Memory")).toBeInTheDocument();
    expect(screen.getByText("container restarts across this app's pods")).toBeInTheDocument();
    expect(screen.queryByText(/no usage metrics yet/i)).not.toBeInTheDocument();
  });
});
