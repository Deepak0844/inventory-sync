"""One Phase 1 check: log in if needed, read a Listing, write Shopify inventory.

Deliberately simple: one Listing to one Variant, acting on a single reading.
Confirmation reads, multiple Listings and the kill switch arrive in Phases 3
and 4 in `app.engine`. Not responsible for those rules.
"""

from collections.abc import Sequence

from app.core.clock import Clock
from app.flows.extract import Reading, ReadingResult, extract_stock
from app.flows.login import BrowserSession, Credentials, LoginResult, ensure_logged_in
from app.flows.login_codes import CodeSource
from app.flows.session_store import EncryptedSessionStore
from app.flows.supplier_flow import SupplierFlow
from app.shopify.client import InventoryWriter

# PLAN.md section 8: the default quantity when the Supplier shows none.
RESTORE_QUANTITY = 100

_LOGGED_IN = {LoginResult.LOGGED_IN, LoginResult.SESSION_REUSED}


def check_listing(
    session: BrowserSession,
    store: EncryptedSessionStore,
    flow: SupplierFlow,
    credentials: Credentials,
    code_sources: Sequence[CodeSource],
    clock: Clock,
    listing_url: str,
    variant_id: str,
    writer: InventoryWriter,
    code_timeout: float,
    poll: float,
) -> Reading:
    """Check one Listing and update its Variant in Shopify.

    Out of Stock and Listing Removed set inventory to 0; In Stock sets it to
    RESTORE_QUANTITY. Unknown, including a failed login, writes nothing.

    Raises:
        ShopifyError: from the writer, if the inventory update fails.
    """
    login = ensure_logged_in(session, store, flow, credentials, code_sources, clock,
                             code_timeout, poll)
    if login not in _LOGGED_IN:
        return Reading(ReadingResult.UNKNOWN, f"login_{login.value}")
    reading = extract_stock(session.page, flow, listing_url)
    if reading.result in (ReadingResult.OUT_OF_STOCK, ReadingResult.LISTING_REMOVED):
        writer.set_available(variant_id, 0)
    elif reading.result is ReadingResult.IN_STOCK:
        writer.set_available(variant_id, RESTORE_QUANTITY)
    return reading
