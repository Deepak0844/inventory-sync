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
from app.flows.page import BrowserSession, Page
from app.mail.codes import MailMessage
from app.shopify.client import InventoryWriter
from app.shopify.orders import OrderReader
from app.shopify.variants import VariantSource


class ShopifyApi(InventoryWriter, OrderReader, VariantSource, Protocol):
    """Writes inventory, reads orders and reads Variants."""


class ManualBrowser(Protocol):
    """An ordinary browser window a person is using."""

    def is_running(self) -> bool:
        """Whether the window is still open."""
        ...


class ProfileSession(Protocol):
    """A headless look at a browser profile: one page, and what it stores."""

    @property
    def page(self) -> Page:
        """The tab to look at."""
        ...

    def storage_state_json(self) -> str:
        """Cookies and origin storage as JSON."""
        ...


BrowserFactory = Callable[[], AbstractContextManager[BrowserSession]]
ManualBrowserFactory = Callable[[Path, str], AbstractContextManager[ManualBrowser]]
ProfileBrowserFactory = Callable[[Path], AbstractContextManager[ProfileSession]]
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
    # Only the manual-browser worker sets these two; see `app.worker.manual_login`.
    manual_browser: ManualBrowserFactory | None = None
    profile_browser: ProfileBrowserFactory | None = None
    poll_s: float = 2.0
    data_dir: Path = Path("data")

    def now(self) -> datetime:
        """The clock's time as a timezone-aware datetime."""
        return datetime.fromtimestamp(self.clock.now(), UTC)
