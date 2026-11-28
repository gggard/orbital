import { afterEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import CopyField from "./CopyField";

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("CopyField", () => {
  it("renders plain text without a link", () => {
    render(<CopyField value="abc" />);
    expect(screen.getByText("abc").tagName).toBe("SPAN");
  });

  it("renders a link when href is given", () => {
    render(<CopyField value="my-app.example.com" href="https://my-app.example.com" />);
    const link = screen.getByRole("link", { name: "my-app.example.com" });
    expect(link).toHaveAttribute("href", "https://my-app.example.com");
    expect(link).toHaveAttribute("target", "_blank");
  });

  it("copies to the clipboard and briefly shows a check mark", () => {
    vi.useFakeTimers();
    const writeText = vi.fn();
    vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } });
    render(<CopyField value="secret" />);

    fireEvent.click(screen.getByRole("button"));
    expect(writeText).toHaveBeenCalledWith("secret");
    expect(screen.getByTestId("CheckIcon")).toBeInTheDocument();

    act(() => vi.advanceTimersByTime(1500));
    expect(screen.getByTestId("ContentCopyIcon")).toBeInTheDocument();
  });
});
