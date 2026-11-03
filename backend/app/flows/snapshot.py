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
# Dropped with their content; `ammonia` would otherwise keep the text of a <script>.
_DROP_WITH_CONTENT = {"script", "style", "iframe", "object", "embed", "svg", "math", "noscript",
                      "template", "head", "title"}
_SAFE_DATA_IMAGE = re.compile(r"^data:image/(png|jpe?g|gif|webp);base64,[A-Za-z0-9+/=]+$", re.I)
_UNSAFE_STYLE = re.compile(r"url\s*\(|expression|@import|javascript|behavior|-moz-binding", re.I)


def _keep(tag: str, attribute: str, value: str) -> str | None:
    """Decide one attribute: return the value to keep, or None to drop it."""
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

    Scripts, frames, plugins, event handlers, external links and images, and
    risky styles are removed, and no input keeps its value. Ids, classes,
    names, `data-*` and `aria-*` attributes stay, because the selector picker
    builds selectors from them.
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
    return f'<!doctype html><html><head><meta charset="utf-8"></head><body>{body}</body></html>'
