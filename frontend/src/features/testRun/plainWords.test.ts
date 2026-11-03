import { errorKindText, loginResultText, readingText, startErrors, stateText, stepName } from "./plainWords";

it("names each node type the way the editor palette does", () => {
  expect(stepName("goto")).toBe("Go to URL");
  expect(stepName("fill")).toBe("Fill");
  expect(stepName("click")).toBe("Click");
  expect(stepName("wait_for")).toBe("Wait for");
  expect(stepName("await_code")).toBe("Wait for a code");
  expect(stepName("branch")).toBe("Branch");
  expect(stepName("save_session")).toBe("Save session");
});

it("shows an unknown node type as it is", () => {
  expect(stepName("teleport")).toBe("teleport");
});

it("describes the run states", () => {
  expect(stateText("queued")).toBe("Queued");
  expect(stateText("running")).toBe("Running");
  expect(stateText("waiting_for_code")).toBe("Waiting for a code");
  expect(stateText("done")).toBe("Done");
  expect(stateText("failed")).toBe("Failed");
});

it("describes each reading", () => {
  expect(readingText("in_stock")).toBe("In stock");
  expect(readingText("out_of_stock")).toBe("Out of stock");
  expect(readingText("listing_removed")).toBe("Listing removed");
  expect(readingText("unknown")).toBe("Unknown");
});

it("explains why a reading is Unknown in plain words", () => {
  expect(errorKindText("flow_failure")).toBe("The stock element wasn't found on the page.");
  expect(errorKindText("session_lost")).toBe("The Supplier asked for a login, so the saved session was lost.");
  expect(errorKindText("blocked")).toBe("The Supplier showed a block or CAPTCHA page.");
  expect(errorKindText("no_rule_matched")).toBe("The stock text matched neither the in-stock rule nor the out-of-stock rule.");
  expect(errorKindText("browser_error")).toBe("The browser couldn't load the page in time.");
});

it("shows an error kind it does not know as it is", () => {
  expect(errorKindText("odd_thing")).toBe("odd_thing");
});

it("describes each login result", () => {
  expect(loginResultText("logged_in")).toBe("Logged in");
  expect(loginResultText("session_reused")).toBe("Reused the saved session");
  expect(loginResultText("wrong_code")).toBe("The Supplier refused the code");
  expect(loginResultText("bad_credentials")).toBe("The Supplier refused the username or password");
  expect(loginResultText("code_timeout")).toBe("No code arrived in time");
  expect(loginResultText("blocked")).toBe("The Supplier showed a block or CAPTCHA page");
  expect(loginResultText("browser_error")).toBe("The browser couldn't load the page in time");
  expect(loginResultText("flow_failure")).toBe("A step in the flow didn't find its element");
  expect(loginResultText("mystery")).toBe("mystery");
});

describe("startErrors", () => {
  it("lists each validation message with where it is", () => {
    const error = { status: 422, data: { detail: [{ loc: ["body", "flow", "nodes", 0, "url"], msg: "must not be empty" }] } };
    expect(startErrors(error)).toEqual(["flow.nodes.0.url: must not be empty"]);
  });

  it("passes on a plain message", () => {
    expect(startErrors({ status: 422, data: { detail: "flow has a cycle" } })).toEqual(["flow has a cycle"]);
  });

  it("falls back to a sentence that says what to do", () => {
    expect(startErrors({ status: "FETCH_ERROR", error: "x" })).toEqual(["Couldn't start the test run. Try again."]);
    expect(startErrors(undefined)).toEqual(["Couldn't start the test run. Try again."]);
  });
});
