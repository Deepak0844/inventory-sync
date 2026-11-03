import { resolveSelector } from "./resolve";
import { stableSelector } from "./stableSelector";
import { DUPLICATES, GENERATED, page, PRODUCT, UTILITY } from "./fixtures";

const product = page(PRODUCT);
const q = (doc: Document, css: string): Element => {
  const el = doc.querySelector(css);
  if (!el) throw new Error(`fixture is missing ${css}`);
  return el;
};

describe("preference order", () => {
  it("uses a unique id first", () => {
    expect(stableSelector(q(product, "h1"))).toBe("#title");
  });

  it("then data-testid, ignoring a generated class on the same element", () => {
    expect(stableSelector(q(product, "[data-testid]"))).toBe('[data-testid="add-to-cart"]');
  });

  it("then the name attribute", () => {
    expect(stableSelector(q(product, "input"))).toBe('input[name="email"]');
  });

  it("then aria-label", () => {
    expect(stableSelector(q(product, "[aria-label]"))).toBe('button[aria-label="Open size guide"]');
  });

  it("then unique visible text, written as a Playwright :has-text selector", () => {
    expect(stableSelector(q(product, 'a[href="/cart"]'))).toBe('a:has-text("Cart")');
  });

  it("uses a stable class instead of text when asked to avoid text (for elements whose text changes)", () => {
    expect(stableSelector(q(product, "p"), { avoidText: true })).toBe("p.stock-status");
  });
});

describe("never picks unstable parts", () => {
  const doc = page(GENERATED);

  it("skips ids that look generated", () => {
    const sel = stableSelector(q(doc, '[id="radix-:r3:"] span'));
    expect(sel).not.toContain("radix");
    expect(sel).not.toContain(":r");
  });

  it("skips generated-looking classes (css-1x2y3z, sc-abc123, css-module hashes)", () => {
    const all = [q(doc, ".price"), q(doc, "i")].map((el) => stableSelector(el, { avoidText: true }));
    for (const sel of all) {
      expect(sel).not.toMatch(/css-1x2y3z|sc-abc123|a1B2c/);
    }
  });

  it("skips utility classes such as flex, mt-4 and text-sm", () => {
    const utility = page(UTILITY);
    const sel = stableSelector(q(utility, "p"), { avoidText: true });
    expect(sel).not.toMatch(/\.flex|\.mt-4|\.px-2|\.text-sm|\.font-medium/);
  });
});

describe("duplicates", () => {
  const doc = page(DUPLICATES);

  it("scopes a repeated button by its unique ancestor", () => {
    const sel = stableSelector(q(doc, "#b .buy"));
    expect(sel).toContain("#b");
    expect(resolveSelector(doc, sel)).toEqual([q(doc, "#b .buy")]);
  });

  it("falls back to one nth-of-type under a stable ancestor, not a long chain", () => {
    const sel = stableSelector(q(product, ".size:nth-child(2)"));
    expect(resolveSelector(product, sel)).toEqual([q(product, ".size:nth-child(2)")]);
    expect((sel.match(/nth-of-type/g) ?? []).length).toBeLessThanOrEqual(1);
    expect(sel.length).toBeLessThan(60);
  });

  it("ignores a duplicated id", () => {
    const dup = page('<p id="x">One</p><p id="x">Two</p>');
    const sel = stableSelector(dup.querySelectorAll("p")[1]);
    expect(resolveSelector(dup, sel)).toEqual([dup.querySelectorAll("p")[1]]);
  });
});

describe("text selectors are only used when they identify one element", () => {
  it("does not use single characters", () => {
    expect(stableSelector(q(product, ".size:nth-child(2)"))).not.toContain("has-text");
  });

  it("does not use the glued-together text of a container with several children", () => {
    for (const css of ["header", "nav", "form", "ul"]) {
      expect(stableSelector(q(product, css)), css).not.toContain("has-text");
    }
  });

  it("does use the text of an element with one inline child", () => {
    const doc = page("<button><span>Add to basket</span></button>");
    expect(stableSelector(q(doc, "button"))).toBe('button:has-text("Add to basket")');
  });

  it("does not use text that is long", () => {
    const doc = page("<p>" + "word ".repeat(20) + "</p><p>other</p>");
    expect(stableSelector(q(doc, "p"))).not.toContain("has-text");
  });

  it("escapes quotes in the text", () => {
    const doc = page('<a href="#">Say "hi" now</a>');
    const sel = stableSelector(q(doc, "a"));
    expect(resolveSelector(doc, sel)).toEqual([q(doc, "a")]);
  });
});

describe("always unique", () => {
  const pages: [string, Document][] = [
    ["product", product],
    ["duplicates", page(DUPLICATES)],
    ["generated", page(GENERATED)],
    ["utility", page(UTILITY)],
    ["bare", page("<div><div><div><p>a</p><p>a</p></div></div><div><div><p>a</p></div></div></div>")],
  ];
  for (const [name, doc] of pages) {
    for (const avoidText of [false, true]) {
      it(`every element on the ${name} page resolves to itself (avoidText=${avoidText})`, () => {
        for (const el of Array.from(doc.body.querySelectorAll("*"))) {
          const sel = stableSelector(el, { avoidText });
          expect(resolveSelector(doc, sel), `${el.outerHTML.slice(0, 60)} -> ${sel}`).toEqual([el]);
        }
      });
    }
  }

  it("returns body for body", () => {
    expect(stableSelector(product.body)).toBe("body");
  });
});
