import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import StateChip from "./StateChip";

describe("StateChip", () => {
  it("renders the raw state, capitalized via CSS, when no override label exists", () => {
    render(<StateChip state="running" />);
    expect(screen.getByText("running")).toBeInTheDocument();
  });

  it("renders an overridden label for created", () => {
    render(<StateChip state="created" />);
    expect(screen.getByText("queued")).toBeInTheDocument();
  });

  it("renders an overridden label for build_failed", () => {
    render(<StateChip state="build_failed" />);
    expect(screen.getByText("build failed")).toBeInTheDocument();
  });

  it("falls back to default styling for unknown states", () => {
    render(<StateChip state={"unknown_state" as never} />);
    expect(screen.getByText("unknown_state")).toBeInTheDocument();
  });
});
