import { resolveSelector } from "./resolve";
import { page, PRODUCT } from "./fixtures";

const doc = page(PRODUCT);

it("resolves plain CSS selectors", () => {
  expect(resolveSelector(doc, "#title")).toEqual([doc.getElementById("title")]);
  expect(resolveSelector(doc, ".size")).toHaveLength(3);
});

it("resolves tag:has-text() the way Playwright does: case-insensitive, whitespace-normalised, substring", () => {
  expect(resolveSelector(doc, 'p:has-text("OUT   of stock")')).toEqual([doc.querySelector("p")]);
  expect(resolveSelector(doc, 'a:has-text("car")')).toHaveLength(1);
});

it("counts every element of that tag whose subtree contains the text", () => {
  const nested = page("<div><div>Hello</div></div>");
  expect(resolveSelector(nested, 'div:has-text("hello")')).toHaveLength(2);
});

it("unescapes quotes inside the text", () => {
  const quoted = page('<p>Say "hi"</p>');
  expect(resolveSelector(quoted, 'p:has-text("Say \\"hi\\"")')).toHaveLength(1);
});

it("throws on a selector that is not valid", () => {
  expect(() => resolveSelector(doc, "div[")).toThrow();
});
