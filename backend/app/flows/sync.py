"""One Phase 1 check: log in if needed, read a Listing, write Shopify inventory.

Deliberately simple: one Listing to one Variant, acting on a single reading.
Confirmation reads, multiple Listings and the kill switch arrive in Phases 3
and 4 in `app.engine`. Not responsible for those rules.
"""

from collections.abc import Callable, Sequence

from app.core.clock import Clock
from app.flows.definition import FlowDefinition
from app.flows.login_codes import CodeSource
from app.flows.page import BrowserSession
from app.flows.results import Credentials, LoginResult, Reading, ReadingResult
from app.flows.runner import run_extract, run_login
from app.flows.session_store import EncryptedSessionStore
from app.mail.codes import MailMessage
from app.shopify.client import InventoryWriter

# PLAN.md section 8: the default quantity when the Supplier shows none.
RESTORE_QUANTITY = 100

_LOGGED_IN = {LoginResult.LOGGED_IN, LoginResult.SESSION_REUSED}


def check_listing(
    flow: FlowDefinition,
    session: BrowserSession,
    store: EncryptedSessionStore,
    credentials: Credentials,
    pasted_codes: CodeSource,
    fetch_mail: Callable[[], Sequence[MailMessage]] | None,
    clock: Clock,
    listing_url: str,
    variant_id: str,
    writer: InventoryWriter,
    poll: float,
) -> Reading:
    """Check one Listing and update its Variant in Shopify.

    Out of Stock and Listing Removed set inventory to 0; In Stock sets it to
    RESTORE_QUANTITY (the Supplier's quantity is read but not used until the
    decision engine, Phase 3). Unknown, including a
    failed login, writes nothing.

    Raises:
        ShopifyError: from the writer, if the inventory update fails.
    """
    login = run_login(flow, session, store, credentials, pasted_codes, fetch_mail, clock, poll)
    if login not in _LOGGED_IN:
        return Reading(ReadingResult.UNKNOWN, f"login_{login.value}")
    reading = run_extract(flow, session.page, listing_url)
    if reading.result in (ReadingResult.OUT_OF_STOCK, ReadingResult.LISTING_REMOVED):
        writer.set_available(variant_id, 0)
    elif reading.result is ReadingResult.IN_STOCK:
        writer.set_available(variant_id, RESTORE_QUANTITY)
    return reading
