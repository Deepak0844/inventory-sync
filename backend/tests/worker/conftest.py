"""A small world for worker tests: a Supplier with Variants, fakes for every external system."""

from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.encryption import SecretBox, generate_key
from app.db.repos.catalog import CatalogRepo, ImportRow
from app.db.repos.suppliers import SupplierRepo
from app.mail.codes import MailMessage
from app.shopify.client import ShopifyError
from app.shopify.orders import Order
from app.shopify.variants import ShopVariant
from app.worker.deps import Deps
from tests.fakes import FakeBrowserSession, FakeClock, ScriptedPage, sample_flow_dict

T0 = 1_700_000_000.0
BASE = "http://supplier.test"


class FakeShopify:
    """Records writes; can fail for chosen Variants."""

    def __init__(self) -> None:
        self.writes: list[tuple[str, int]] = []
        self.fail_for: set[str] = set()
        self.orders: list[Order] = []
        self.since: list[str] = []
        self.variants: list[ShopVariant] = []

    def set_available(self, variant_id: str, quantity: int) -> None:
        if variant_id in self.fail_for:
            raise ShopifyError("boom")
        self.writes.append((variant_id, quantity))

    def recent_orders(self, since_iso: str) -> list[Order]:
        self.since.append(since_iso)
        return self.orders

    def all_variants(self) -> list[ShopVariant]:
        return self.variants


class SitePage(ScriptedPage):
    """A logged-in Supplier site: `stock` maps a Listing URL to its stock text."""

    def __init__(self) -> None:
        super().__init__(visible={".me"})
        self.stock: dict[str, str | None] = {}
        self.removed: set[str] = set()
        self.login_page = False

    def goto(self, url: str) -> Any:
        self.url = url
        self.visible.discard("#stock")
        text = self.stock.get(url)
        if text is not None:
            self.visible.add("#stock")
            self.texts["#stock"] = text
        self.status = 404 if url in self.removed else 200
        if self.login_page and "/p/" in url:
            self.url = f"{BASE}/login"
        return super().goto(url)


@dataclass
class World:
    session: Session
    deps: Deps
    clock: FakeClock
    box: SecretBox
    page: SitePage
    shopify: FakeShopify
    supplier_id: int
    gids: list[str] = field(default_factory=list)
    mail: list[MailMessage] = field(default_factory=list)

    def now(self) -> datetime:
        return datetime.fromtimestamp(self.clock.now(), UTC)

    def set_stock(self, *texts: str | None) -> None:
        for i, text in enumerate(texts, start=1):
            self.page.stock[f"{BASE}/p/{i}"] = text


def build_deps(session_factory: Callable[[], Session], box: SecretBox, clock: FakeClock,
               page: SitePage, shopify: FakeShopify, mail: list[MailMessage]) -> Deps:
    return Deps(
        session_factory=session_factory, box=box, clock=clock,
        browser=lambda: nullcontext(FakeBrowserSession(page)),
        shopify=lambda settings, secrets: shopify,
        mail=lambda settings, secrets: (lambda: mail),
        poll_s=1.0,
    )


@pytest.fixture
def make_world(db_session: Session, db_engine: Engine) -> Callable[..., World]:
    def make(variants: int = 3, **supplier_fields: Any) -> World:
        box = SecretBox(generate_key())
        clock = FakeClock(T0)
        page, shopify = SitePage(), FakeShopify()
        mail: list[MailMessage] = []
        factory = sessionmaker(bind=db_engine)
        now = datetime.fromtimestamp(T0, UTC)
        suppliers = SupplierRepo(db_session, box)
        sid = suppliers.create("Supplier A", BASE, now, **supplier_fields).id
        suppliers.set_credentials(sid, "owner", "s3cret")
        suppliers.set_flow(sid, sample_flow_dict())
        catalog = CatalogRepo(db_session)
        gids = []
        for i in range(1, variants + 1):
            gids.append(f"gid://shopify/ProductVariant/{i}")
            catalog.upsert_variant(gids[-1], f"SKU{i}", f"Shirt {i}")
            catalog.import_rows([ImportRow(f"SKU{i}", sid, f"{BASE}/p/{i}", "")])
        deps = build_deps(factory, box, clock, page, shopify, mail)
        world = World(db_session, deps, clock, box, page, shopify, sid, gids, mail)
        # A saved session that still works, so checks do not have to log in.
        from app.db.repos.suppliers import SessionCookiesRepo
        from app.flows.session_store import EncryptedSessionStore
        EncryptedSessionStore(box, SessionCookiesRepo(db_session, sid, world.now)).save("[]")
        return world

    return make

