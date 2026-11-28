import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import LogsTab from "./LogsTab";

const mutate = vi.fn();
const useAppLogs = vi.fn();
vi.mock("@/lib/api", () => ({
  useAppLogs: (id: string, follow: boolean) => useAppLogs(id, follow),
}));

beforeEach(() => {
  mutate.mockReset();
  useAppLogs.mockReset().mockReturnValue({ data: "hello\nworld", mutate });
});

afterEach(() => vi.restoreAllMocks());

describe("LogsTab", () => {
  it("follows logs by default and can stop following", () => {
    render(<LogsTab appId="a1" />);
    expect(screen.getByText(/hello/)).toBeInTheDocument();
    expect(useAppLogs).toHaveBeenLastCalledWith("a1", true);

    fireEvent.click(screen.getByRole("switch"));
    expect(useAppLogs).toHaveBeenLastCalledWith("a1", false);
  });

  it("refreshes on demand", () => {
    render(<LogsTab appId="a1" />);
    fireEvent.click(screen.getByTestId("RefreshIcon").closest("button")!);
    expect(mutate).toHaveBeenCalled();
  });

  it("downloads the current logs as a text file", () => {
    // jsdom has no object URLs, so install stand-ins and put the originals back afterwards
    const original = { create: URL.createObjectURL, revoke: URL.revokeObjectURL };
    const createObjectURL = vi.fn(() => "blob:logs");
    const revokeObjectURL = vi.fn();
    URL.createObjectURL = createObjectURL;
    URL.revokeObjectURL = revokeObjectURL;
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    try {
      render(<LogsTab appId="a1" />);
      fireEvent.click(screen.getByTestId("DownloadIcon").closest("button")!);

      expect(createObjectURL).toHaveBeenCalledWith(expect.any(Blob));
      expect(click).toHaveBeenCalled();
      expect(revokeObjectURL).toHaveBeenCalledWith("blob:logs");
    } finally {
      URL.createObjectURL = original.create;
      URL.revokeObjectURL = original.revoke;
    }
  });

  it("shows placeholders while loading and for empty output", () => {
    useAppLogs.mockReturnValue({ data: undefined, mutate });
    const { rerender } = render(<LogsTab appId="a1" />);
    expect(screen.getByText("loading…")).toBeInTheDocument();

    useAppLogs.mockReturnValue({ data: "", mutate });
    rerender(<LogsTab appId="a1" />);
    expect(screen.getByText("— no output —")).toBeInTheDocument();
  });
});
