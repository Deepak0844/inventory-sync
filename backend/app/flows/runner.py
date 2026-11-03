"""Walks a flow definition: node by node for login, and the extract rules for a Listing.

Knows nothing about individual node types; each node does its own work behind
`BaseNode.run`. Not responsible for deciding what a reading means for Shopify.
"""

import re
from collections.abc import Callable, Sequence
from typing import Protocol
from urllib.parse import urlparse

from app.core.clock import Clock
from app.core.encryption import DecryptionError
from app.flows.definition import FlowDefinition
from app.flows.login_codes import CodeSource
from app.flows.nodes import FlowContext, FlowFailure, FlowNode
from app.flows.page import BrowserSession, Page, PageError
from app.flows.results import Credentials, LoginResult, Reading, ReadingResult
from app.flows.session_store import EncryptedSessionStore
from app.mail.codes import MailMessage


class StepObserver(Protocol):
    """Told after each node, for Test runs that show every step."""

    def after_node(self, node: FlowNode, error: str | None) -> None:
        """Called once per node with None on success, or a message that holds no secrets."""
        ...


def run_login(
    flow: FlowDefinition,
    session: BrowserSession,
    store: EncryptedSessionStore,
    credentials: Credentials,
    pasted_codes: CodeSource,
    fetch_mail: Callable[[], Sequence[MailMessage]] | None,
    clock: Clock,
    poll: float,
    *,
    observer: StepObserver | None = None,
    stop_after: str | None = None,
    use_saved_session: bool = True,
) -> LoginResult:
    """Make the session logged in, running the login nodes only if the saved session is gone.

    Never raises for a browser or flow problem; the result says what happened.
    The keyword arguments are for Test runs: `observer` hears about each node,
    `stop_after` ends the walk after that node id (the result is then LOGGED_IN
    only in the sense that no node failed; FLOW_FAILURE if the path taken never
    reaches that node, for example the other side of a branch), and `use_saved_session=False` runs
    the nodes even when a saved session still works.
    """
    ctx = FlowContext(session, store, credentials, pasted_codes, fetch_mail, clock, poll)
    try:
        if use_saved_session and _saved_session_works(flow, ctx):
            return LoginResult.SESSION_REUSED
        _walk(flow, ctx, observer, stop_after)
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
        ctx.session.load_storage_state_json(saved)
    except (ValueError, PageError):
        # Corrupt value: drop it so it does not break every later run.
        ctx.store.clear()
        ctx.session.clear_storage_state()
        return False
    ctx.session.page.goto(flow.logged_in_url)
    if ctx.session.page.is_visible(flow.logged_in_marker):
        return True
    ctx.store.clear()
    ctx.session.clear_storage_state()
    return False


def _is_blocked(flow: FlowDefinition, page: Page) -> bool:
    """Whether the page SHOWS the blocked text. Only visible text counts: ordinary pages carry
    words like "captcha" in their scripts (a Shopify login page has it 78 times), and reading
    the raw HTML made every such page look blocked."""
    return flow.blocked_if.contains.lower() in page.inner_text("body").lower()


def _step(flow: FlowDefinition, ctx: FlowContext, node: FlowNode) -> str | None:
    label = node.run(ctx)
    if _is_blocked(flow, ctx.session.page):
        raise FlowFailure(LoginResult.BLOCKED, "blocked page")
    return label


def _walk(
    flow: FlowDefinition, ctx: FlowContext, observer: StepObserver | None,
    stop_after: str | None,
) -> None:
    node = flow.start
    while True:
        try:
            label = _step(flow, ctx, node)
        except (FlowFailure, PageError) as exc:
            if observer is not None:
                observer.after_node(node, str(exc))
            raise
        if observer is not None:
            observer.after_node(node, None)
        if node.id == stop_after:
            return
        following = flow.next_node(node.id, label)
        if following is None:
            if stop_after is not None:
                # The walk ended on a path that never touched the node: say so rather than
                # let a Test run show the end of the flow as if it were that step.
                raise FlowFailure(LoginResult.FLOW_FAILURE, f"{stop_after} was not reached")
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
    if _is_blocked(flow, page):
        return Reading(ReadingResult.UNKNOWN, "blocked")
    if urlparse(page.url).path.startswith(flow.login_path):
        return Reading(ReadingResult.UNKNOWN, "session_lost")
    if not page.is_visible(rules.stock_selector):
        return Reading(ReadingResult.UNKNOWN, "flow_failure")
    text = page.inner_text(rules.stock_selector).strip().lower()
    # Out-of-stock wording is checked first because it can contain in-stock wording.
    if rules.out_of_stock_if.contains.lower() in text:
        return Reading(ReadingResult.OUT_OF_STOCK, matched_rule="out_of_stock_if")
    if rules.in_stock_if.contains.lower() in text:
        return Reading(ReadingResult.IN_STOCK, quantity=_quantity(flow, page),
                       matched_rule="in_stock_if")
    return Reading(ReadingResult.UNKNOWN, "no_rule_matched")


def _quantity(flow: FlowDefinition, page: Page) -> int | None:
    selector = flow.extract.quantity_selector
    if selector is None or not page.is_visible(selector):
        return None
    match = re.search(r"\d+", page.inner_text(selector))
    return int(match.group()) if match else None
