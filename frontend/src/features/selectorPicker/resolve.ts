const HAS_TEXT = /^([a-z][a-z0-9-]*):has-text\("((?:[^"\\]|\\.)*)"\)$/i;

const normalise = (text: string): string => text.replace(/\s+/g, " ").trim().toLowerCase();

/**
 * Find the elements a selector means in `doc`. Plain CSS goes to the browser; `tag:has-text("…")`,
 * which the worker's Playwright understands and CSS does not, is matched the way Playwright does:
 * case-insensitive, whitespace-normalised, any element of that tag whose subtree contains the text.
 * Throws on a selector that is not valid.
 */
export function resolveSelector(doc: Document, selector: string): Element[] {
  const text = HAS_TEXT.exec(selector);
  if (!text) return Array.from(doc.querySelectorAll(selector));
  const wanted = normalise(text[2].replace(/\\(.)/g, "$1"));
  return Array.from(doc.querySelectorAll(text[1])).filter((el) => normalise(el.textContent ?? "").includes(wanted));
}
