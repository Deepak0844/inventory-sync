import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { DataTable, type Column } from "./DataTable";

interface Row { id: number; name: string; qty: number | null }
const columns: Column<Row>[] = [
  { key: "name", header: "Name", cell: (r) => r.name },
  { key: "qty", header: "Quantity", numeric: true, cell: (r) => r.qty },
];
const rows: Row[] = [{ id: 1, name: "Blue / L", qty: 7 }, { id: 2, name: "Red / M", qty: null }];

it("renders rows, a total and right-aligned numbers", () => {
  render(<DataTable columns={columns} rows={rows} rowKey={(r) => r.id} total={1203} noun="variants" />);
  expect(screen.getByText("1,203 variants")).toBeInTheDocument();
  expect(screen.getByText("7")).toHaveClass("text-right");
});

it("prints a grey dash for a missing value but a real zero as 0", () => {
  render(
    <DataTable
      columns={columns}
      rows={[{ id: 1, name: "A", qty: 0 }, { id: 2, name: "B", qty: null }]}
      rowKey={(r) => r.id}
      total={2}
      noun="variants"
    />,
  );
  expect(screen.getByText("0")).toBeInTheDocument();
  expect(screen.getByText("–")).toBeInTheDocument();
});

it("shows an empty state that keeps the header", () => {
  render(<DataTable columns={columns} rows={[]} rowKey={(r) => r.id} total={0} noun="variants" empty="No variants yet." />);
  expect(screen.getByText("Quantity")).toBeInTheDocument();
  expect(screen.getByText("No variants yet.")).toBeInTheDocument();
});

it("shows a loading layout without values", () => {
  render(<DataTable columns={columns} rows={[]} rowKey={(r) => r.id} total={0} noun="variants" loading />);
  expect(screen.getByText("Quantity")).toBeInTheDocument();
  expect(screen.getAllByTestId("skeleton-row").length).toBeGreaterThan(0);
});

it("shows an error inside the block with a Retry button", async () => {
  const onRetry = vi.fn();
  render(
    <DataTable columns={columns} rows={[]} rowKey={(r) => r.id} total={0} noun="variants"
      error="Couldn't load variants. Last updated 09:14." onRetry={onRetry} />,
  );
  expect(screen.getByText("Couldn't load variants. Last updated 09:14.")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Retry" }));
  expect(onRetry).toHaveBeenCalled();
});

it("offers load more at the end when there are more rows", async () => {
  const onLoadMore = vi.fn();
  render(<DataTable columns={columns} rows={rows} rowKey={(r) => r.id} total={5} noun="variants" onLoadMore={onLoadMore} />);
  await userEvent.click(screen.getByRole("button", { name: "Load more" }));
  expect(onLoadMore).toHaveBeenCalled();
});
