import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { Palette } from "./Palette";

it("lists every step type that can be added", () => {
  render(<Palette onAdd={() => {}} />);
  for (const name of ["Go to URL", "Fill", "Click", "Wait for", "Await code", "Branch", "Save session"]) {
    expect(screen.getByRole("button", { name })).toBeEnabled();
  }
});

it("adds the step type that was clicked", async () => {
  const onAdd = vi.fn();
  render(<Palette onAdd={onAdd} />);
  await userEvent.click(screen.getByRole("button", { name: "Branch" }));
  expect(onAdd).toHaveBeenCalledWith("branch");
});

it("shows the Code step as not built yet", () => {
  render(<Palette onAdd={() => {}} />);
  expect(screen.getByRole("button", { name: /Code/ })).toBeDisabled();
  expect(screen.getByText(/coming later/i)).toBeInTheDocument();
});

it("makes each button draggable onto the canvas", () => {
  render(<Palette onAdd={() => {}} />);
  expect(screen.getByRole("button", { name: "Click" })).toHaveAttribute("draggable", "true");
});
