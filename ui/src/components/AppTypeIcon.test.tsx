import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import AppTypeIcon from "./AppTypeIcon";

describe("AppTypeIcon", () => {
  it("labels static apps as a static site", async () => {
    render(<AppTypeIcon appType="static" />);
    expect(await screen.findByLabelText("Static site")).toBeInTheDocument();
  });

  it("labels streamlit apps as a streamlit app", async () => {
    render(<AppTypeIcon appType="streamlit" />);
    expect(await screen.findByLabelText("Streamlit app")).toBeInTheDocument();
  });
});
