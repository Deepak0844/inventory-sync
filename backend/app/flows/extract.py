"""Reading a Listing's Stock Status from its page.

Anything that is not a clear In Stock or Out of Stock reading is Unknown, which
never changes Shopify. Not responsible for deciding what to do with a reading.
"""

from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlparse

from app.flows.page import Page, PageError
from app.flows.supplier_flow import SupplierFlow


class ReadingResult(Enum):
    """Outcome of reading one Listing."""

    IN_STOCK = "in_stock"
    OUT_OF_STOCK = "out_of_stock"
    LISTING_REMOVED = "listing_removed"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Reading:
    """One reading. `error_kind` explains an UNKNOWN result."""

    result: ReadingResult
    error_kind: str | None = None


def _unknown(kind: str) -> Reading:
    return Reading(ReadingResult.UNKNOWN, kind)


def extract_stock(page: Page, flow: SupplierFlow, listing_url: str) -> Reading:
    """Open the Listing and read its stock element.

    Never raises for a page problem; a failed check is an Unknown reading.
    """
    try:
        return _read(page, flow, listing_url)
    except PageError:
        return _unknown("browser_error")


def _read(page: Page, flow: SupplierFlow, listing_url: str) -> Reading:
    response = page.goto(listing_url)
    if response is not None and response.status == 404:
        return Reading(ReadingResult.LISTING_REMOVED)
    if flow.blocked_text in page.content():
        return _unknown("blocked")
    if urlparse(page.url).path.startswith(flow.login_path):
        return _unknown("session_lost")
    if not page.is_visible(flow.stock_selector):
        return _unknown("flow_failure")
    text = page.inner_text(flow.stock_selector).strip().lower()
    # Out-of-stock wording is checked first because it can contain in-stock wording.
    if any(phrase in text for phrase in flow.out_of_stock_texts):
        return Reading(ReadingResult.OUT_OF_STOCK)
    if any(phrase in text for phrase in flow.in_stock_texts):
        return Reading(ReadingResult.IN_STOCK)
    return _unknown("no_rule_matched")
