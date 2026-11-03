import { render, screen } from "@testing-library/react";

import { ReadingStrip } from "./ReadingStrip";

it("draws one tick per reading with an accessible description", () => {
  render(
    <ReadingStrip
      readings={[
        { result: "in_stock", read_at: "2026-11-03T10:00:00Z" },
        { result: "out_of_stock", read_at: "2026-11-03T10:30:00Z" },
        { result: "out_of_stock", read_at: "2026-11-03T11:00:00Z" },
        { result: "unknown", read_at: "2026-11-03T11:30:00Z" },
      ]}
    />,
  );
  expect(screen.getAllByTestId("tick")).toHaveLength(4);
  expect(screen.getByRole("img")).toHaveAccessibleName(
    "Last 4 readings: In stock, Out of stock, Out of stock, Unknown",
  );
});

it("marks each tick by result so colour is not the only signal", () => {
  render(
    <ReadingStrip
      readings={[
        { result: "in_stock", read_at: "2026-11-03T10:00:00Z" },
        { result: "out_of_stock", read_at: "2026-11-03T10:30:00Z" },
        { result: "unknown", read_at: "2026-11-03T11:00:00Z" },
      ]}
    />,
  );
  expect(screen.getAllByTestId("tick").map((t) => t.dataset.result)).toEqual([
    "in_stock", "out_of_stock", "unknown",
  ]);
});

it("shows a grey dash when there are no readings", () => {
  render(<ReadingStrip readings={[]} />);
  expect(screen.getByText("–")).toBeInTheDocument();
});
