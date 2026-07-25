import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import SecretsTab from "./SecretsTab";

const mockUseSecrets = vi.fn();
const mockPutSecrets = vi.fn();
const mockMutate = vi.fn();
vi.mock("@/lib/api", () => ({
  useSecrets: (id: string) => mockUseSecrets(id),
  putSecrets: (id: string, value: string) => mockPutSecrets(id, value),
}));

describe("SecretsTab", () => {
  it("shows a skeleton while loading", () => {
    mockUseSecrets.mockReturnValue({ data: undefined, isLoading: true, mutate: mockMutate });
    const { container } = render(<SecretsTab appId="a1" onSaved={vi.fn()} />);
    expect(container.querySelector(".MuiSkeleton-root")).toBeInTheDocument();
  });

  it("initializes the editor with the fetched secrets once loaded", () => {
    mockUseSecrets.mockReturnValue({
      data: 'api_key = "abc"',
      isLoading: false,
      mutate: mockMutate,
    });
    render(<SecretsTab appId="a1" onSaved={vi.fn()} />);
    expect(screen.getByDisplayValue('api_key = "abc"')).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /save & restart app/i })).toBeDisabled();
  });

  it("enables save once edited, and discard reverts to the fetched value", () => {
    mockUseSecrets.mockReturnValue({
      data: 'api_key = "abc"',
      isLoading: false,
      mutate: mockMutate,
    });
    render(<SecretsTab appId="a1" onSaved={vi.fn()} />);

    fireEvent.change(screen.getByDisplayValue('api_key = "abc"'), {
      target: { value: 'api_key = "changed"' },
    });
    expect(screen.getByRole("button", { name: /save & restart app/i })).toBeEnabled();

    fireEvent.click(screen.getByRole("button", { name: /discard changes/i }));
    expect(screen.getByDisplayValue('api_key = "abc"')).toBeInTheDocument();
  });

  it("saves, revalidates without a refetch, and calls onSaved", async () => {
    mockPutSecrets.mockResolvedValue(undefined);
    mockUseSecrets.mockReturnValue({
      data: 'api_key = "abc"',
      isLoading: false,
      mutate: mockMutate,
    });
    const onSaved = vi.fn();
    render(<SecretsTab appId="a1" onSaved={onSaved} />);

    fireEvent.change(screen.getByDisplayValue('api_key = "abc"'), {
      target: { value: 'api_key = "changed"' },
    });
    fireEvent.click(screen.getByRole("button", { name: /save & restart app/i }));

    await vi.waitFor(() => expect(mockMutate).toHaveBeenCalled());
    expect(mockPutSecrets).toHaveBeenCalledWith("a1", 'api_key = "changed"');
    expect(mockMutate).toHaveBeenCalledWith('api_key = "changed"', { revalidate: false });
    expect(onSaved).toHaveBeenCalled();
  });

  it("shows an error message when saving fails", async () => {
    mockPutSecrets.mockRejectedValue(new Error("network down"));
    mockUseSecrets.mockReturnValue({
      data: 'api_key = "abc"',
      isLoading: false,
      mutate: mockMutate,
    });
    render(<SecretsTab appId="a1" onSaved={vi.fn()} />);

    fireEvent.change(screen.getByDisplayValue('api_key = "abc"'), {
      target: { value: 'api_key = "changed"' },
    });
    fireEvent.click(screen.getByRole("button", { name: /save & restart app/i }));

    expect(await screen.findByText(/network down/i)).toBeInTheDocument();
  });
});
