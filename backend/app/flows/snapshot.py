"""Cleaning a Supplier page so it is safe to show in the selector picker.

The cleaned copy is rendered in a sandboxed frame in the dashboard, so nothing
in it may run or load anything. Not responsible for taking the snapshot.
"""

import re

import nh3

_TAGS = {
    "a", "article", "aside", "b", "blockquote", "br", "button", "caption", "dd", "div",
    "dl", "dt", "em", "fieldset", "figcaption", "figure", "footer", "form", "h1", "h2", "h3", "h4",
    "h5", "h6", "header", "hr", "i", "img", "input", "label", "legend", "li", "main",
    "nav", "ol", "optgroup", "option", "p", "pre", "section", "select", "small", "span", "strong",
    "sub", "sup", "table", "tbody", "td", "tfoot", "th", "thead", "tr", "u", "ul",
}
_ATTRIBUTES = {
    "*": {"id", "class", "name", "type", "placeholder", "alt", "title", "role", "for", "style",
          "value", "disabled", "checked", "selected", "colspan", "rowspan", "lang", "dir",
          "href", "src"},
}
# Dropped with their content; `ammonia` would otherwise keep the text of a <script> or <textarea>.
_DROP_WITH_CONTENT = {"script", "style", "iframe", "object", "embed", "svg", "math", "noscript",
                      "template", "head", "title", "textarea"}
# The only data-* attributes worth keeping: they are meant as stable test hooks. Any other
# data-* may hold a CSRF token, a user email or an API key.
_DATA_KEPT = {"data-testid", "data-test", "data-cy"}
# nh3 escapes quotes and angle brackets inside attribute values, so in its output one
# `<input ...>` is exactly what this matches and `type="hidden"` cannot hide in a value.
_HIDDEN_INPUT = re.compile(r'<input\b[^>]*\stype="hidden"[^>]*>', re.I)
_SAFE_DATA_IMAGE = re.compile(r"^data:image/(png|jpe?g|gif|webp);base64,[A-Za-z0-9+/=]+$", re.I)
_UNSAFE_STYLE = re.compile(r"url\s*\(|expression|@import|javascript|behavior|-moz-binding", re.I)


def _keep(tag: str, attribute: str, value: str) -> str | None:
    """Decide one attribute: return the value to keep, or None to drop it."""
    if attribute.startswith("data-") and attribute not in _DATA_KEPT:
        return None
    if attribute == "src":
        return value if tag == "img" and _SAFE_DATA_IMAGE.match(value) else None
    if attribute == "href":
        return value if value.startswith("#") else None  # nothing external to follow
    if attribute == "style":
        return None if _UNSAFE_STYLE.search(value) else value
    if attribute == "value" and tag == "input":
        # The picker only needs the structure. Dropping every input value also covers
        # passwords, codes, tokens and hidden CSRF fields without guessing by name.
        return None
    return value


def clean_snapshot_html(html: str) -> str:
    """Return a safe, static copy of a page as a complete HTML document.

    Removed: scripts, styles with URLs, frames, plugins, SVG, templates, `<noscript>`
    and `<textarea>` (with their text), `<meta>` and `<head>`, event handlers, external
    links and images, risky styles, every `<input type="hidden">`, and the value of every
    input (which covers passwords and codes without guessing by name), plus every `data-*`
    attribute except `data-testid`, `data-test` and `data-cy`.

    Kept: the visible text of the page, and ids, classes, names, `aria-*` attributes,
    placeholders and labels, because the selector picker builds selectors from them. Text
    that the page itself shows (a name, an order number) is therefore still in the copy;
    only values hidden in attributes, hidden fields and text areas are not.
    """
    body = nh3.clean(
        html,
        tags=_TAGS,
        clean_content_tags=_DROP_WITH_CONTENT,
        attributes=_ATTRIBUTES,
        generic_attribute_prefixes={"data-", "aria-"},
        attribute_filter=_keep,
        url_schemes={"data"},
        link_rel=None,
        strip_comments=True,
    )
    body = _HIDDEN_INPUT.sub("", body)
    return f'<!doctype html><html><head><meta charset="utf-8"></head><body>{body}</body></html>'
