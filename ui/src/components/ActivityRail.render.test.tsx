import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import type { ActivityEvent } from "@/lib/types";
import ActivityRail from "./ActivityRail";

const mockUseActivity = vi.fn();
vi.mock("@/lib/api", () => ({
  useActivity: (enabled: boolean) => mockUseActivity(enabled),
}));

function event(overrides: Partial<ActivityEvent>): ActivityEvent {
  return {
    id: "e1",
    slug: "sales-dash",
    text: "redeployed successfully",
    level: "success",
    actor: "j.alvarez",
    created_at: new Date().toISOString(),
    ...overrides,
  };
}

describe("ActivityRail", () => {
  it("renders nothing when disabled (non-admin)", () => {
    mockUseActivity.mockReturnValue({ data: undefined, isLoading: false });
    const { container } = render(<ActivityRail enabled={false} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows a loading skeleton", () => {
    mockUseActivity.mockReturnValue({ data: undefined, isLoading: true });
    const { container } = render(<ActivityRail enabled />);
    expect(container.querySelector(".MuiSkeleton-root")).toBeInTheDocument();
  });

  it("shows an empty message when there are no events", () => {
    mockUseActivity.mockReturnValue({ data: [], isLoading: false });
    render(<ActivityRail enabled />);
    expect(screen.getByText("No recent activity.")).toBeInTheDocument();
  });

  it("renders events with slug, text, actor and relative time", () => {
    mockUseActivity.mockReturnValue({
      data: [event({ slug: "sales-dash", text: "redeployed successfully", actor: "j.alvarez" })],
      isLoading: false,
    });
    render(<ActivityRail enabled />);
    expect(screen.getByText("sales-dash")).toBeInTheDocument();
    expect(screen.getByText(/redeployed successfully/)).toBeInTheDocument();
    expect(screen.getByText(/j\.alvarez/)).toBeInTheDocument();
  });

  it("links to the fleet admin page", () => {
    mockUseActivity.mockReturnValue({ data: [], isLoading: false });
    render(<ActivityRail enabled />);
    expect(screen.getByRole("link", { name: /view all activity/i })).toHaveAttribute(
      "href",
      "/admin",
    );
  });
});
