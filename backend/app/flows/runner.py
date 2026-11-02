"""Walks a flow definition: node by node for login, and the extract rules for a Listing.

Knows nothing about individual node types; each node does its own work behind
`BaseNode.run`. Not responsible for deciding what a reading means for Shopify.
"""

import re
from collections.abc import Callable, Sequence
from urllib.parse import urlparse

from app.core.clock import Clock
from app.core.encryption import DecryptionError
from app.flows.definition import FlowDefinition
from app.flows.login_codes import CodeSource
from app.flows.nodes import FlowContext, FlowFailure
from app.flows.page import BrowserSession, Page, PageError
from app.flows.results import Credentials, LoginResult, Reading, ReadingResult
from app.flows.session_store import EncryptedSessionStore
from app.mail.codes import MailMessage


def run_login(
    flow: FlowDefinition,
    session: BrowserSession,
    store: EncryptedSessionStore,
    credentials: Credentials,
    pasted_codes: CodeSource,
    fetch_mail: Callable[[], Sequence[MailMessage]] | None,
    clock: Clock,
    poll: float,
) -> LoginResult:
    """Make the session logged in, running the login nodes only if the saved session is gone.

    Never raises for a browser or flow problem; the result says what happened.
    """
    ctx = FlowContext(session, store, credentials, pasted_codes, fetch_mail, clock, poll)
    try:
        if _saved_session_works(flow, ctx):
            return LoginResult.SESSION_REUSED
        _walk(flow, ctx)
    except FlowFailure as failure:
        return failure.result
    except PageError:
        return LoginResult.BROWSER_ERROR
    return LoginResult.LOGGED_IN


def _saved_session_works(flow: FlowDefinition, ctx: FlowContext) -> bool:
    try:
        saved = ctx.store.load()
    except DecryptionError:
        # Key rotated or value corrupt: the session is unusable, so log in afresh.
        saved = None
    if saved is None:
        return False
    try:
        ctx.session.load_cookies_json(saved)
    except (ValueError, PageError):
        # Corrupt value: drop it so it does not break every later run.
        ctx.store.clear()
        ctx.session.clear_cookies()
        return False
    ctx.session.page.goto(flow.logged_in_url)
    if ctx.session.page.is_visible(flow.logged_in_marker):
        return True
    ctx.store.clear()
    ctx.session.clear_cookies()
    return False


def _walk(flow: FlowDefinition, ctx: FlowContext) -> None:
    node = flow.start
    while True:
        label = node.run(ctx)
        if flow.blocked_if.contains.lower() in ctx.session.page.content().lower():
            raise FlowFailure(LoginResult.BLOCKED)
        following = flow.next_node(node.id, label)
        if following is None:
            return
        node = following


def run_extract(flow: FlowDefinition, page: Page, listing_url: str) -> Reading:
    """Open the Listing and read its stock element.

    Never raises for a page problem; a failed check is an Unknown reading.
    """
    try:
        return _read(flow, page, listing_url)
    except PageError:
        return Reading(ReadingResult.UNKNOWN, "browser_error")


def _read(flow: FlowDefinition, page: Page, listing_url: str) -> Reading:
    rules = flow.extract
    response = page.goto(listing_url)
    if response is not None and response.status == 404:
        return Reading(ReadingResult.LISTING_REMOVED)
    if flow.blocked_if.contains.lower() in page.content().lower():
        return Reading(ReadingResult.UNKNOWN, "blocked")
    if urlparse(page.url).path.startswith(flow.login_path):
        return Reading(ReadingResult.UNKNOWN, "session_lost")
    if not page.is_visible(rules.stock_selector):
        return Reading(ReadingResult.UNKNOWN, "flow_failure")
    text = page.inner_text(rules.stock_selector).strip().lower()
    # Out-of-stock wording is checked first because it can contain in-stock wording.
    if rules.out_of_stock_if.contains.lower() in text:
        return Reading(ReadingResult.OUT_OF_STOCK)
    if rules.in_stock_if.contains.lower() in text:
        return Reading(ReadingResult.IN_STOCK, quantity=_quantity(flow, page))
    return Reading(ReadingResult.UNKNOWN, "no_rule_matched")


def _quantity(flow: FlowDefinition, page: Page) -> int | None:
    selector = flow.extract.quantity_selector
    if selector is None or not page.is_visible(selector):
        return None
    match = re.search(r"\d+", page.inner_text(selector))
    return int(match.group()) if match else None
