"""The real implementations of what `Deps` asks for: Shopify, the mailbox and the browser.

Not responsible for the worker loop (`app.worker.jobs`).
"""

from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from datetime import timedelta

import httpx
from playwright.sync_api import sync_playwright

from app.core.clock import Clock
from app.db.repos.settings import SettingsRecord, SettingsSecrets
from app.flows.playwright_session import PlaywrightSupplierSession
from app.mail.codes import MailMessage
from app.mail.imap import ImapMailbox
from app.shopify.auth import ClientCredentialsToken
from app.shopify.client import ShopifyClient
from app.shopify.orders import Order, ShopifyOrderReader
from app.shopify.variants import ShopifyVariantReader, ShopVariant
from app.worker.deps import ShopifyApi

MAILBOX_LOOKBACK = timedelta(minutes=30)


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
