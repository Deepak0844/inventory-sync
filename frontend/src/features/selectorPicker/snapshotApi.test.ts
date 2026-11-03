import { snapshotPath } from "./snapshotApi";

it("turns the contract's /api path into one relative to the API base", () => {
  expect(snapshotPath("/api/test-runs/1/files/snapshot.html")).toBe("/test-runs/1/files/snapshot.html");
});

it("leaves an absolute URL alone", () => {
  const url = "http://localhost:3000/api/test-runs/1/files/snapshot.html";
  expect(snapshotPath(url)).toBe(url);
});
