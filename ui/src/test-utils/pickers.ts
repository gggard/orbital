import { fireEvent, screen, within } from "@testing-library/react";

/** Type a free-text value into a multi-select Autocomplete (TagPicker/GroupPicker) and press Enter. */
export function addChip(label: string, value: string) {
  const input = screen.getByLabelText(label);
  fireEvent.change(input, { target: { value } });
  fireEvent.keyDown(input, { key: "Enter" });
}

/** Remove a chip by clicking its delete icon. */
export function removeChip(text: string) {
  const chip = screen.getByText(text).closest(".MuiChip-root") as HTMLElement;
  fireEvent.click(within(chip).getByTestId("CancelIcon"));
}
