"""The real implementations of what `Deps` asks for: Shopify, the mailbox and the browser.

Not responsible for the worker loop (`app.worker.jobs`).
"""

import json
import signal
import subprocess
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path

import httpx
from playwright.sync_api import Error, sync_playwright

from app.core.clock import Clock
from app.db.repos.settings import SettingsRecord, SettingsSecrets
from app.flows.chromium_cookies import ProfileCookieError, read_cookies
from app.flows.page import PageError
from app.flows.playwright_session import PlaywrightSupplierSession
from app.mail.codes import MailMessage
from app.mail.imap import ImapMailbox
from app.shopify.auth import ClientCredentialsToken
from app.shopify.client import ShopifyClient
from app.shopify.orders import Order, ShopifyOrderReader
from app.shopify.variants import ShopifyVariantReader, ShopVariant
from app.worker.deps import ShopifyApi

MAILBOX_LOOKBACK = timedelta(minutes=30)
CLOSE_TIMEOUT_S = 15.0


class ShopifyFacade:
    """One Shopify client presented as the writer, order reader and Variant reader."""

    def __init__(self, client: ShopifyClient) -> None:
        self._client = client

    def set_available(self, variant_id: str, quantity: int) -> None:
        """Set a Variant's available quantity."""
        self._client.set_available(variant_id, quantity)

    def recent_orders(self, since_iso: str) -> list[Order]:
        """Return orders created since `since_iso`."""
        return ShopifyOrderReader(self._client).recent_orders(since_iso)

    def all_variants(self) -> list[ShopVariant]:
        """Return every Variant that has a SKU."""
        return ShopifyVariantReader(self._client).all_variants()


class RealShopifyFactory:
    """Builds a Shopify API from the saved settings, keeping each token until it expires."""

    def __init__(
        self, clock: Clock, transport: Callable[[], httpx.BaseTransport] = httpx.HTTPTransport
    ) -> None:
        self._clock = clock
        self._transport = transport
        self._tokens: dict[tuple[str, str, str], ClientCredentialsToken] = {}

    def __call__(self, settings: SettingsRecord, secrets: SettingsSecrets) -> ShopifyApi | None:
        """Return the API, or None if the shop, app id or secret is missing.

        Raises:
            ShopifyError: if Shopify refuses to give a token.
        """
        if not (settings.shop_domain and settings.client_id and secrets.client_secret):
            return None
        key = (settings.shop_domain, settings.client_id, secrets.client_secret)
        if key not in self._tokens:
            self._tokens[key] = ClientCredentialsToken(*key, self._transport(), self._clock)
        client = ShopifyClient(settings.shop_domain, self._tokens[key].token(),
                               self._transport(), self._clock)
        return ShopifyFacade(client)


def imap_fetch(
    settings: SettingsRecord, secrets: SettingsSecrets
) -> Callable[[], Sequence[MailMessage]] | None:
    """Return a function reading recent mail, or None if the mailbox is not set up."""
    if not (settings.mailbox_host and settings.mailbox_user and secrets.mailbox_password):
        return None
    return ImapMailbox(settings.mailbox_host, settings.mailbox_user, secrets.mailbox_password,
                       MAILBOX_LOOKBACK).recent_messages


@contextmanager
def chromium() -> Iterator[PlaywrightSupplierSession]:
    """A fresh headless Chromium and isolated browser context for one visit."""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            with PlaywrightSupplierSession(browser) as session:
                yield session
        finally:
            browser.close()


class PlainChromium:
    """A Chromium process a person is using. Nothing is attached to control it."""

    def __init__(self, process: subprocess.Popen[bytes]) -> None:
        self._process = process

    def is_running(self) -> bool:
        """Whether the browser is still open."""
        return self._process.poll() is None

    def stop(self) -> None:
        """Close the browser and wait, so its cookies are on disk before anyone reads them.

        SIGINT, not SIGTERM: Chromium saves its cookies on SIGINT, but SIGTERM exits at once and
        drops every cookie changed in the last ~30 seconds, which is the login that just happened.
        SIGTERM and then SIGKILL are only for a browser that ignores the first request.
        """
        for sig in (signal.SIGINT, signal.SIGTERM):
            if self._process.poll() is not None:
                return
            self._process.send_signal(sig)
            try:
                self._process.wait(timeout=CLOSE_TIMEOUT_S)
                return
            except subprocess.TimeoutExpired:
                continue
        self._process.kill()
        self._process.wait()


@contextmanager
def plain_chromium(
    profile_dir: Path, url: str, executable: str | None = None
) -> Iterator[PlainChromium]:
    """Open Chromium as an ordinary program on the container's display, closed on exit.

    It is deliberately not started through Playwright: remote control marks the browser as
    automated (`navigator.webdriver`), and a Supplier's CAPTCHA can then reject a correct answer.
    `--no-sandbox` is needed because the container has no user namespaces; this browser only
    ever opens the Supplier's login page inside that private container. The basic password
    store matches Playwright's, so `headless_profile` can read the cookies afterwards.

    Raises:
        PageError: if the program cannot be started.
    """
    try:
        path = executable or _chromium_path()
        _keep_session_cookies(profile_dir)
        process = subprocess.Popen(
            [path, f"--user-data-dir={profile_dir}", "--no-first-run",
             "--no-default-browser-check", "--password-store=basic", "--no-sandbox",
             "--disable-background-networking", "--disable-sync", "--disable-component-update",
             "--window-position=0,0", "--window-size=1440,900", url],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except (OSError, Error) as exc:
        raise PageError("could not start Chromium for the manual login") from exc
    browser = PlainChromium(process)
    try:
        yield browser
    finally:
        browser.stop()


def _keep_session_cookies(profile_dir: Path) -> None:
    """Make Chromium save cookies that have no expiry, which many Supplier logins use.

    It only does so when it is set to restore the last session, so a plain close would
    otherwise lose the login before the worker reads the profile.
    """
    default = profile_dir / "Default"
    default.mkdir(parents=True, exist_ok=True)
    (default / "Preferences").write_text(json.dumps({"session": {"restore_on_startup": 1}}))


def _chromium_path() -> str:
    with sync_playwright() as playwright:
        return playwright.chromium.executable_path


@contextmanager
def headless_profile(profile_dir: Path) -> Iterator[PlaywrightSupplierSession]:
    """A headless browser holding the cookies a person just logged in with.

    The profile is not reopened by Chromium, because it drops cookies with no expiry when it
    does; its cookie file is read directly instead (`app.flows.chromium_cookies`).

    Raises:
        PageError: if the profile's cookies cannot be read.
    """
    try:
        cookies = read_cookies(profile_dir)
    except ProfileCookieError as exc:
        raise PageError("could not read the cookies from the browser profile") from exc
    with chromium() as session:
        session.load_storage_state_json(json.dumps({"cookies": cookies, "origins": []}))
        yield session
