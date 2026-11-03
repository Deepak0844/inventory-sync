import { ReactFlowProvider } from "@xyflow/react";
import { render, screen } from "@testing-library/react";

import { draftFromFlow } from "./builderState";
import { FlowCanvas } from "./FlowCanvas";
import { branchFlow, sampleFlow } from "./testData";
import { installBrowserShims } from "./testSupport";

beforeAll(() => installBrowserShims());

const show = (flow = sampleFlow(), problems: Record<string, string[]> = {}, readOnly = false) =>
  render(
    <ReactFlowProvider>
      <FlowCanvas draft={draftFromFlow(flow)} problems={problems} readOnly={readOnly} onChange={() => {}} onAdd={() => {}} />
    </ReactFlowProvider>,
  );

it("shows each step as a card with its type as text and what it does", () => {
  show();
  expect(screen.getByText("Go to URL")).toBeInTheDocument();
  expect(screen.getByText("https://supplier-a.example/login")).toBeInTheDocument();
  expect(screen.getAllByText("Fill")).toHaveLength(3);
  expect(screen.getByText("Save session")).toBeInTheDocument();
});

it("says what a Wait for step is waiting for", () => {
  show();
  expect(screen.getByText(/\.account-menu/)).toBeInTheDocument();
});

it("shows a step's first problem on its card", () => {
  show(sampleFlow(), { n4: ["Pick or enter a selector.", "Another."] });
  expect(screen.getByText("Pick or enter a selector.")).toBeInTheDocument();
  expect(screen.queryByText("Another.")).not.toBeInTheDocument();
});

it("labels the two paths out of a Branch", () => {
  show(branchFlow());
  expect(screen.getByText("Branch")).toBeInTheDocument();
  expect(screen.getAllByText("yes").length).toBeGreaterThan(0);
  expect(screen.getAllByText("no").length).toBeGreaterThan(0);
});
