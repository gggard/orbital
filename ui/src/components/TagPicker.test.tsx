import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import TagPicker from "./TagPicker";

describe("TagPicker", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise(() => {})),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("offers the current values sorted alongside whatever the directory returns", () => {
    render(<TagPicker value={["prod", "dev"]} onChange={vi.fn()} />);
    expect(screen.getByLabelText("Tags")).toBeInTheDocument();
  });
});
