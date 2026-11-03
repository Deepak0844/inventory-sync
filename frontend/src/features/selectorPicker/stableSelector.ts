import { resolveSelector } from "./resolve";

export interface SelectorOptions {
  /** Skip text selectors. Use it for the stock element, whose text changes between In Stock and Out of Stock. */
  avoidText?: boolean;
}

// Tokens (ids and classes) that a build tool made up, so they change on the next deploy.
const GENERATED = [
  /:/, // React and Radix ids such as ":r1:" or "radix-:r3:"
  /\d{4,}/,
  /^(?=.*\d)(css|sc|jsx|svelte|emotion|styled)[-_][a-z0-9]{4,}$/i,
  /^_(?=.*\d)[a-z0-9]{4,}$/i,
  /__(?=.*\d)(?=.*[a-z])[a-z0-9_-]{5,}$/i, // CSS-module hash: "Button_primary__a1B2c"
  /^(?=.*\d)(?=.*[a-z])[a-z0-9]{6,}$/i, // random mixed letters and digits
];
// Tailwind-style utilities describe looks, not meaning, and repeat all over a page.
const UTILITY =
  /^(?:-?(?:m|p)[trblxy]?-\S+|(?:w|h|min-w|max-w|min-h|max-h|gap|space-[xy]|text|bg|border|rounded|font|leading|tracking|items|justify|self|z|top|left|right|bottom|opacity|shadow)-\S+|flex|grid|block|inline|inline-block|inline-flex|hidden|relative|absolute|fixed|sticky|truncate|container|sr-only)$/;
const SIMPLE_NAME = /^[A-Za-z_][\w-]*$/;
const MIN_TEXT = 2;
const MAX_TEXT = 40;
const MAX_ANCESTORS = 4;
const MAX_CLASSES = 2;

const looksGenerated = (token: string): boolean => GENERATED.some((pattern) => pattern.test(token));
const attr = (name: string, value: string): string => `[${name}="${value.replace(/["\\]/g, "\\$&")}"]`;
const usable = (value: string | null): value is string => !!value && !/[\n\r\t]/.test(value);

function isUnique(el: Element, selector: string): boolean {
  try {
    const found = resolveSelector(el.ownerDocument, selector);
    return found.length === 1 && found[0] === el;
  } catch {
    return false;
  }
}

function stableClasses(el: Element): string[] {
  return Array.from(el.classList).filter((c) => SIMPLE_NAME.test(c) && !looksGenerated(c) && !UTILITY.test(c));
}

const INLINE = new Set(["a", "span", "strong", "em", "b", "i", "small", "abbr", "code", "label", "svg"]);

/** Text identifies a leaf-like element (a link, a button, a heading), not a container of several. */
function isLeafLike(el: Element): boolean {
  const kids = Array.from(el.children);
  return kids.length === 0 || (kids.length === 1 && INLINE.has(kids[0].localName));
}

function textSelector(el: Element): string | null {
  if (!isLeafLike(el)) return null;
  const text = (el.textContent ?? "").replace(/\s+/g, " ").trim();
  if (text.length < MIN_TEXT || text.length > MAX_TEXT || !/[\p{L}\p{N}]/u.test(text)) return null;
  return `${el.localName}:has-text("${text.replace(/["\\]/g, "\\$&")}")`;
}

/** The first of id, data-testid, name, aria-label, text, then own classes that picks `el` alone. */
function identity(el: Element, options: SelectorOptions): string | null {
  const tag = el.localName;
  const id = el.getAttribute("id");
  const testId = el.getAttribute("data-testid");
  const name = el.getAttribute("name");
  const label = el.getAttribute("aria-label");
  const candidates: (string | null)[] = [
    id && SIMPLE_NAME.test(id) && !looksGenerated(id) ? `#${id}` : null,
    usable(testId) && !looksGenerated(testId) ? attr("data-testid", testId) : null,
    usable(name) ? `${tag}${attr("name", name)}` : null,
    usable(label) ? `${tag}${attr("aria-label", label)}` : null,
    options.avoidText ? null : textSelector(el),
  ];
  const classes = stableClasses(el);
  if (classes.length > 0) {
    candidates.push(...classes.map((c) => `${tag}.${c}`));
    if (classes.length > 1) candidates.push(`${tag}.${classes.slice(0, MAX_CLASSES).join(".")}`);
  }
  return candidates.find((c): c is string => c !== null && isUnique(el, c)) ?? null;
}

/** A selector built from one stable ancestor, kept short: at most one `:nth-of-type`. */
function anchored(el: Element, options: SelectorOptions): string | null {
  const tag = el.localName;
  const parent = el.parentElement;
  const classes = stableClasses(el);
  const position = parent ? Array.from(parent.children).filter((c) => c.localName === tag).indexOf(el) + 1 : 0;
  let ancestor = parent;
  for (let depth = 0; ancestor && ancestor.localName !== "body" && depth < MAX_ANCESTORS; depth++) {
    const anchor = identity(ancestor, { ...options, avoidText: true });
    if (anchor) {
      const tries = [
        ...(classes.length > 0 ? [`${anchor} ${tag}.${classes[0]}`] : []),
        `${anchor} ${tag}`,
        ...(ancestor === parent ? [`${anchor} > ${tag}:nth-of-type(${position})`] : []),
        `${anchor} ${tag}:nth-of-type(${position})`,
      ];
      const hit = tries.find((t) => isUnique(el, t));
      if (hit) return hit;
    }
    ancestor = ancestor.parentElement;
  }
  return null;
}

/** Last resort, rooted at body so it is always unique. Rare on real pages. */
function fullPath(el: Element): string {
  const parts: string[] = [];
  for (let node: Element | null = el; node && node.localName !== "body"; node = node.parentElement) {
    const same = node.parentElement ? Array.from(node.parentElement.children).filter((c) => c.localName === node.localName) : [];
    parts.unshift(same.length > 1 ? `${node.localName}:nth-of-type(${same.indexOf(node) + 1})` : node.localName);
  }
  return ["body", ...parts].join(" > ");
}

/**
 * The most stable selector that picks exactly `el` in its document, for the worker's Playwright.
 * Prefers an id, `data-testid`, `name`, `aria-label`, then unique text (`tag:has-text("…")`, unless
 * `avoidText`), then a stable class, then a short path under a stable ancestor. Ids and classes that
 * look generated are never used. The result is always checked against the document.
 */
export function stableSelector(el: Element, options: SelectorOptions = {}): string {
  const tag = el.localName;
  if (tag === "body" || tag === "html") return tag;
  return identity(el, options) ?? anchored(el, options) ?? fullPath(el);
}
