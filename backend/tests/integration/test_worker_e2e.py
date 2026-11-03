"""The worker end to end: real Chromium, the mock Supplier, a fake Shopify and a fake clock.

Lives beside the other browser tests so they share one session-wide Playwright (two sync
Playwrights cannot run in one process).
"""

import json
import socket
import threading
import time
from collections.abc import Callable, Iterator, Sequence
from datetime import UTC, datetime

import pytest
import uvicorn
from playwright.sync_api import Browser
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.encryption import SecretBox, generate_key
from app.db.repos.approvals import ApprovalRepo
from app.db.repos.catalog import CatalogRepo, ImportRow
from app.db.repos.jobs import JobRecord
from app.db.repos.notifications import NotificationRepo
from app.db.repos.suppliers import SupplierRepo
from app.flows.playwright_session import PlaywrightSupplierSession
from app.mail.codes import MailMessage
from app.worker.check import handle_check_supplier
from app.worker.deps import Deps
from mock_supplier.app import MockState, create_mock_app
from tests.fakes import FakeClock
from tests.integration.conftest import RunningMock, mock_flow_json
from tests.worker.conftest import T0, FakeShopify

IN, OUT = "In stock", "Out of stock"


@pytest.fixture
def mock_clock() -> FakeClock:
    return FakeClock(T0)


@pytest.fixture
def mock_supplier(mock_clock: FakeClock) -> Iterator[RunningMock]:
    """The mock Supplier on a real port, stamping emails with the test's fake clock.

    The half second keeps an email strictly newer than the click that caused it.
    """
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    state = MockState(clock=lambda: mock_clock.now() + 0.5)
    server = uvicorn.Server(uvicorn.Config(create_mock_app(state), port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.02)
    yield RunningMock(f"http://127.0.0.1:{port}", state)
    server.should_exit = True
    thread.join(timeout=5)


class Site:
    def __init__(self, session: Session, deps: Deps, mock: RunningMock, shopify: FakeShopify,
                 clock: FakeClock, supplier_id: int, gids: list[str]) -> None:
        self.session, self.deps, self.mock, self.shopify = session, deps, mock, shopify
        self.clock, self.supplier_id, self.gids = clock, supplier_id, gids

    def check(self) -> None:
        with self.deps.session_factory() as s:
            handle_check_supplier(self.deps, s, JobRecord(1, "check_supplier", self.supplier_id,
                                                          {}, 0))

    def flip(self, *product_ids: int, in_stock: bool) -> None:
        for i in product_ids:
            self.mock.control(f"stock/{i}", in_stock=in_stock)

    def later(self, seconds: float) -> None:
        self.clock.sleep(seconds)

    def kinds(self) -> list[str]:
        return [n.kind for n in NotificationRepo(self.session).list(resolved=False)]


@pytest.fixture
def site(db_session: Session, db_engine: Engine, browser: Browser, mock_supplier: RunningMock,
         mock_clock: FakeClock) -> Callable[..., Site]:
    def build(listings: int = 4, wrong_code: bool = False) -> Site:
        box, shopify = SecretBox(generate_key()), FakeShopify()

        def fetch() -> Sequence[MailMessage]:
            if wrong_code:
                return [MailMessage("no-reply@mock-supplier.test", "Your code is 000000",
                                    mock_clock.now() + 1)]
            return [MailMessage(str(m["sender"]), str(m["body"]), float(m["sent_at"]))  # type: ignore[arg-type]
                    for m in mock_supplier.outbox()]

        deps = Deps(
            session_factory=sessionmaker(bind=db_engine), box=box, clock=mock_clock,
            browser=lambda: PlaywrightSupplierSession(browser),
            shopify=lambda settings, secrets: shopify, mail=lambda settings, secrets: fetch,
            poll_s=1.0)
        now = datetime.fromtimestamp(T0, UTC)
        suppliers = SupplierRepo(db_session, box)
        sid = suppliers.create("Mock Supplier", mock_supplier.base_url, now,
                               two_fa_methods=["email_code"]).id
        suppliers.set_credentials(sid, "shop", "pw")
        suppliers.set_flow(sid, json.loads(mock_flow_json(mock_supplier.base_url)))
        catalog, gids = CatalogRepo(db_session), []
        for i in range(1, listings + 1):
            gids.append(f"gid://shopify/ProductVariant/{i}")
            catalog.upsert_variant(gids[-1], f"SKU{i}", f"Shirt {i}")
            catalog.import_rows([ImportRow(f"SKU{i}", sid,
                                           f"{mock_supplier.base_url}/product/{i}", "")])
        return Site(db_session, deps, mock_supplier, shopify, mock_clock, sid, gids)

    return build


def test_a_stock_flip_sells_the_variant_out_after_two_reads_half_an_hour_apart(
    site: Callable[..., Site],
) -> None:
    s = site()
    s.check()  # logs in with the emailed code, everything In Stock
    assert sorted(w for w in s.shopify.writes) == sorted((g, 100) for g in s.gids)
    s.flip(1, in_stock=False)
    s.later(7200)
    s.check()  # first Out of Stock reading: nothing is sold out yet
    assert (s.gids[0], 0) not in s.shopify.writes
    s.later(1800)
    s.check()  # second reading, half an hour later: confirmed
    assert (s.gids[0], 0) in s.shopify.writes
    s.flip(1, in_stock=True)
    s.later(7200)
    s.shopify.writes.clear()
    s.check()
    assert (s.gids[0], 100) in s.shopify.writes  # restored after one In Stock reading


def test_a_redesigned_page_reads_unknown_and_never_writes(site: Callable[..., Site]) -> None:
    s = site()
    s.check()
    s.shopify.writes.clear()
    s.mock.control("selector", changed=True)
    s.later(7200)
    s.check()
    assert s.shopify.writes == []
    assert "flow_failure" in s.kinds()


def test_a_mass_flip_is_held_for_approval_and_changes_nothing(site: Callable[..., Site]) -> None:
    s = site()
    s.check()
    s.flip(1, 2, 3, 4, in_stock=False)
    s.later(7200)
    s.check()
    s.later(1800)
    s.shopify.writes.clear()
    s.check()
    assert s.shopify.writes == []
    pending = ApprovalRepo(s.session).list_pending()
    assert len(pending) == 1 and len(pending[0].changes) == 4
    assert "pending_approval" in s.kinds()


def test_a_wrong_code_twice_pauses_the_supplier(site: Callable[..., Site]) -> None:
    s = site(wrong_code=True)
    s.check()
    supplier = SupplierRepo(s.session, s.deps.box).get(s.supplier_id)
    assert supplier is not None and supplier.paused and supplier.failed_login_attempts == 2
    assert "login_attention" in s.kinds() and s.shopify.writes == []
