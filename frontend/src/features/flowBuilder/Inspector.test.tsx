import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { Inspector } from "./Inspector";
import { sampleFlow } from "./testData";
import type { FlowDoc, FlowNode } from "./types";

const setup = (selected: FlowNode | null, flow: FlowDoc = sampleFlow(), picking: string | null = null) => {
  const props = {
    selected,
    meta: flow,
    onNode: vi.fn(),
    onMeta: vi.fn(),
    onExtract: vi.fn(),
    onPick: vi.fn(),
    picking,
    pickVersion: 0,
    readOnly: false,
  };
  render(<Inspector {...props} />);
  return props;
};
const node = (id: string) => sampleFlow().nodes.find((n) => n.id === id) as FlowNode;

it("edits the address of a Go to URL step", async () => {
  const p = setup(node("n1"));
  const field = screen.getByLabelText("Page address");
  await userEvent.clear(field);
  await userEvent.type(field, "https://new.example");
  expect(p.onNode).toHaveBeenLastCalledWith({ id: "n1", type: "goto", url: "https://new.example" });
});

it("edits a Fill step, including the mask option", async () => {
  const p = setup(node("n2"));
  await userEvent.click(screen.getByLabelText("Hide the value in screenshots"));
  expect(p.onNode).toHaveBeenLastCalledWith(expect.objectContaining({ id: "n2", mask: true }));
  expect(screen.getByLabelText("Value to type")).toHaveValue("{{credentials.username}}");
});

it("picks a Wait for role and keeps the other fields", async () => {
  const p = setup(node("n9"));
  await userEvent.selectOptions(screen.getByLabelText("What this waits for"), "code_prompt");
  expect(p.onNode).toHaveBeenLastCalledWith(expect.objectContaining({ id: "n9", role: "code_prompt", selector: ".account-menu" }));
});

it("shows the email details only when the code can arrive by email", async () => {
  const p = setup({ ...(node("n6") as FlowNode), methods: ["ui_code"] } as FlowNode);
  expect(screen.queryByLabelText("Sender")).not.toBeInTheDocument();
  await userEvent.click(screen.getByLabelText("Mailbox"));
  expect(p.onNode).toHaveBeenLastCalledWith(expect.objectContaining({ methods: ["ui_code", "email_code"] }));
});

it("edits the sender and pattern of an Await code step", async () => {
  const p = setup(node("n6"));
  const sender = screen.getByLabelText("Sender");
  await userEvent.clear(sender);
  await userEvent.type(sender, "a@b.c");
  expect(p.onNode).toHaveBeenLastCalledWith(expect.objectContaining({ email: expect.objectContaining({ sender: "a@b.c" }) }));
});

it("edits the element a Branch looks for", async () => {
  const p = setup({ id: "b1", type: "branch", if_visible: "" });
  await userEvent.type(screen.getByLabelText("Element to look for"), "#otp");
  expect(p.onNode).toHaveBeenLastCalledWith({ id: "b1", type: "branch", if_visible: "#otp" });
});

it("says a Save session step has nothing to set", () => {
  setup(node("n10"));
  expect(screen.getByText(/nothing to set/i)).toBeInTheDocument();
});

it("asks to pick a selector from the page and says which field is waiting", async () => {
  const p = setup(node("n4"));
  const button = screen.getByRole("button", { name: "Pick selector for Selector" });
  expect(button).toHaveTextContent("Pick from page");
  await userEvent.click(button);
  expect(p.onPick).toHaveBeenCalledWith("selector");
});

it("shows the field that is waiting for a pick as active", () => {
  setup(node("n4"), sampleFlow(), "selector");
  const button = screen.getByRole("button", { name: "Cancel selector pick for Selector" });
  expect(button).toHaveAttribute("aria-pressed", "true");
  expect(button).toHaveTextContent("Cancel");
  expect(screen.getByText("Now click an element in the Page preview below.")).toBeInTheDocument();
});

it("stops waiting for a pick once the person types the selector themselves", async () => {
  const p = setup(node("n4"), sampleFlow(), "selector");
  await userEvent.type(screen.getByLabelText("Selector"), "x");
  expect(p.onPick).toHaveBeenCalledWith("selector");
  expect(p.onPick).toHaveBeenCalledTimes(1);
});

it("does not touch the pick state when typing into a field that is not waiting", async () => {
  const p = setup(node("n4"));
  await userEvent.type(screen.getByLabelText("Selector"), "x");
  expect(p.onPick).not.toHaveBeenCalled();
});

it("shows the flow settings and the stock rules when no step is selected", async () => {
  const p = setup(null);
  expect(screen.getByLabelText("Login page path")).toHaveValue("/login");
  const path = screen.getByLabelText("Login page path");
  await userEvent.clear(path);
  await userEvent.type(path, "/in");
  expect(p.onMeta).toHaveBeenLastCalledWith({ login_path: "/in" });
  const stock = screen.getByLabelText("Stock element");
  await userEvent.type(stock, "x");
  expect(p.onExtract).toHaveBeenLastCalledWith({ stock_selector: ".stock-statusx" });
  expect(screen.getByLabelText("Text that means In stock")).toHaveValue("In stock");
});

it("marks fields that are empty as needing a value", async () => {
  setup({ id: "n1", type: "goto", url: "" });
  await userEvent.type(screen.getByLabelText("Page address"), "a");
  await userEvent.clear(screen.getByLabelText("Page address"));
  expect(await screen.findByText("Enter the page address.")).toBeInTheDocument();
});

it("cannot be edited when read only", () => {
  render(
    <Inspector selected={node("n1")} meta={sampleFlow()} onNode={() => {}} onMeta={() => {}} onExtract={() => {}}
      onPick={() => {}} picking={null} pickVersion={0} readOnly />,
  );
  expect(screen.getByLabelText("Page address")).toBeDisabled();
});
