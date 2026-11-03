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

interface Item { id: number; url: string; status: string; qty: number | null; last: string | null; note: string }
const phoneColumns: Column<Item>[] = [
  { key: "url", header: "Listing", phone: "primary", cell: (r) => r.url },
  { key: "status", header: "Status", phone: "key", cell: (r) => r.status },
  { key: "qty", header: "Quantity", numeric: true, phone: "secondary", cell: (r) => r.qty },
  { key: "last", header: "Last success", cell: (r) => r.last },
  { key: "note", header: "Note", phone: "hidden", cell: (r) => r.note },
];
const items: Item[] = [{ id: 1, url: "shop.test/a", status: "In stock", qty: 7, last: "2h ago", note: "n" }];
const renderItems = () =>
  render(<DataTable columns={phoneColumns} rows={items} rowKey={(r) => r.id} total={1} noun="listings" />);

it("marks each cell with its place in the two-line phone row", () => {
  renderItems();
  expect(screen.getByText("shop.test/a").closest("td")).toHaveAttribute("data-phone", "primary");
  expect(screen.getByText("In stock").closest("td")).toHaveAttribute("data-phone", "key");
  expect(screen.getByText("7").closest("td")).toHaveAttribute("data-phone", "secondary");
});

it("treats a column with no phone role as secondary", () => {
  renderItems();
  expect(screen.getByText("2h ago").closest("td")).toHaveAttribute("data-phone", "secondary");
});

it("labels secondary cells so a bare number is not ambiguous on a phone", () => {
  renderItems();
  expect(screen.getByText("7").closest("td")).toHaveAttribute("data-label", "Quantity");
  expect(screen.getByText("shop.test/a").closest("td")).not.toHaveAttribute("data-label");
});

it("hides a phone-hidden column below the tablet breakpoint only", () => {
  renderItems();
  expect(screen.getByText("n").closest("td")).toHaveClass("max-md:hidden");
  expect(screen.getByText("Note").closest("th")).not.toHaveClass("max-md:hidden");
});

it("hides the header row on a phone", () => {
  renderItems();
  expect(screen.getByText("Listing").closest("thead")).toHaveClass("max-md:hidden");
});

it("puts one line break between the first and second phone line of each row", () => {
  renderItems();
  expect(screen.getAllByTestId("phone-break")).toHaveLength(1);
});

it("uses the first column as the phone primary when none is declared", () => {
  render(<DataTable columns={columns} rows={rows} rowKey={(r) => r.id} total={2} noun="variants" />);
  expect(screen.getByText("Blue / L").closest("td")).toHaveAttribute("data-phone", "primary");
  expect(screen.getByText("7").closest("td")).toHaveAttribute("data-phone", "secondary");
});

it("keeps rows at least a touch target tall on a phone", () => {
  renderItems();
  expect(screen.getByText("shop.test/a").closest("tr")).toHaveClass("max-md:min-h-touch");
});

it("keeps the primary on one line and reads secondary values inline on a phone", () => {
  renderItems();
  expect(screen.getByText("shop.test/a").closest("span")).toHaveClass("max-md:truncate");
  expect(screen.getByText("7").closest("span")).toHaveClass("max-md:inline");
});
