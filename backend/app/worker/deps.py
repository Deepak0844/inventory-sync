"""Everything the worker needs from outside, passed in so tests can use fakes.

Not responsible for building the real implementations (`app.worker.real`).
"""

from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.encryption import SecretBox
from app.db.repos.settings import SettingsRecord, SettingsSecrets
from app.flows.page import BrowserSession
from app.mail.codes import MailMessage
from app.shopify.client import InventoryWriter
from app.shopify.orders import OrderReader
from app.shopify.variants import VariantSource


class ShopifyApi(InventoryWriter, OrderReader, VariantSource, Protocol):
    """Writes inventory, reads orders and reads Variants."""


BrowserFactory = Callable[[], AbstractContextManager[BrowserSession]]
FetchMail = Callable[[], Sequence[MailMessage]]


@dataclass
class Deps:
    """Injected collaborators. `shopify` and `mail` return None when not set up."""

    session_factory: Callable[[], Session]
    box: SecretBox
    clock: Clock
    browser: BrowserFactory
    shopify: Callable[[SettingsRecord, SettingsSecrets], ShopifyApi | None]
    mail: Callable[[SettingsRecord, SettingsSecrets], FetchMail | None]
    poll_s: float = 2.0
    data_dir: Path = Path("data")

    def now(self) -> datetime:
        """The clock's time as a timezone-aware datetime."""
        return datetime.fromtimestamp(self.clock.now(), UTC)
