import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import AnalyticsTab from "./AnalyticsTab";
import type { AnalyticsOut } from "@/lib/types";

let state: { data?: AnalyticsOut; error?: Error; isLoading: boolean };
vi.mock("@/lib/api", () => ({ useAppAnalytics: () => state }));

function analytics(overrides: Partial<AnalyticsOut> = {}): AnalyticsOut {
  return {
    total_views: 1234,
    unique_viewers_1d: 3,
    unique_viewers_7d: 12,
    unique_viewers_30d: 40,
    last_viewed_at: "2026-11-02T10:00:00Z",
    daily: [
      { date: "2026-11-01", views: 10, unique_viewers: 4 },
      { date: "2026-11-02", views: 25, unique_viewers: 7 },
    ],
    viewers: [{ viewer: "dev@example.com", views: 9, last_seen: "2026-11-02T10:00:00Z" }],
    ...overrides,
  };
}

beforeEach(() => {
  state = { isLoading: true };
});

describe("AnalyticsTab", () => {
  it("shows a skeleton while loading", () => {
    const { container } = render(<AnalyticsTab appId="a1" />);
    expect(container.querySelector(".MuiSkeleton-root")).toBeInTheDocument();
  });

  it("shows load errors", () => {
    state = { isLoading: false, error: new Error("timeout") };
    render(<AnalyticsTab appId="a1" />);
    expect(screen.getByText("failed to load analytics: timeout")).toBeInTheDocument();
  });

  it("explains when there are no views yet", () => {
    state = { isLoading: false, data: analytics({ total_views: 0 }) };
    render(<AnalyticsTab appId="a1" />);
    expect(screen.getByText(/no views recorded yet/i)).toBeInTheDocument();
  });

  it("shows stat tiles, daily charts and the viewer table", () => {
    state = { isLoading: false, data: analytics() };
    render(<AnalyticsTab appId="a1" />);
    expect(screen.getByText("Total views")).toBeInTheDocument();
    expect(screen.getByText((1234).toLocaleString())).toBeInTheDocument();
    expect(screen.getByLabelText("Views per day")).toBeInTheDocument();
    expect(screen.getByLabelText("Unique viewers per day")).toBeInTheDocument();
    expect(screen.getAllByText("25").length).toBeGreaterThan(0);
    expect(screen.getByText("dev@example.com")).toBeInTheDocument();
  });

  it("skips charts with a single day and the table without viewers", () => {
    state = {
      isLoading: false,
      data: analytics({
        last_viewed_at: null,
        daily: [{ date: "2026-11-02", views: 5, unique_viewers: 2 }],
        viewers: [],
      }),
    };
    render(<AnalyticsTab appId="a1" />);
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.queryByLabelText("Views per day")).not.toBeInTheDocument();
    expect(screen.queryByText("Viewer")).not.toBeInTheDocument();
  });
});
