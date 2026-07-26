import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import Sparkline from "./Sparkline";

describe("Sparkline", () => {
  it("renders a flat baseline for fewer than 2 samples", () => {
    const { container } = render(<Sparkline values={[42]} color="#000" />);
    expect(container.querySelector("line")).toBeInTheDocument();
    expect(container.querySelector("path")).not.toBeInTheDocument();
  });

  it("renders a flat baseline for zero samples", () => {
    const { container } = render(<Sparkline values={[]} color="#000" />);
    expect(container.querySelector("line")).toBeInTheDocument();
  });

  it("renders line and area paths for 2+ samples", () => {
    const { container } = render(<Sparkline values={[1, 5, 2, 8]} color="#123456" />);
    const paths = container.querySelectorAll("path");
    expect(paths).toHaveLength(2);
    for (const path of paths) {
      expect(
        path.getAttribute("stroke") === "#123456" || path.getAttribute("fill") === "#123456",
      ).toBe(true);
    }
  });

  it("does not crash on a flat (zero-variance) series", () => {
    const { container } = render(<Sparkline values={[3, 3, 3]} color="#000" />);
    expect(container.querySelectorAll("path")).toHaveLength(2);
  });

  it("respects custom width/height", () => {
    const { container } = render(
      <Sparkline values={[1, 2]} color="#000" width={50} height={20} />,
    );
    const svg = container.querySelector("svg");
    expect(svg).toHaveAttribute("width", "50");
    expect(svg).toHaveAttribute("height", "20");
  });
});
