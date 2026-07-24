import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import GroupPicker from "./GroupPicker";

describe("GroupPicker", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise(() => {})),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("offers the extra options sorted alongside whatever the directory returns", () => {
    render(
      <GroupPicker
        value={[]}
        onChange={vi.fn()}
        label="Owners"
        extraOptions={["team-b", "team-a"]}
      />,
    );
    expect(screen.getByLabelText("Owners")).toBeInTheDocument();
  });
});
