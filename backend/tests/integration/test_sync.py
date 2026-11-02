from playwright.sync_api import Browser

from app.core.clock import SystemClock
from app.core.encryption import SecretBox, generate_key
from app.flows.login import Credentials
from app.flows.playwright_session import PlaywrightSupplierSession
from app.flows.session_store import EncryptedSessionStore, MemoryTextRepository
from app.flows.supplier_flow import SupplierFlow
from app.flows.sync import RESTORE_QUANTITY, check_listing
from tests.integration.conftest import RunningMock
from tests.integration.test_supplier_browser import PasteFromOutbox

VARIANT = "gid://shopify/ProductVariant/1"


class FakeWriter:
    def __init__(self) -> None:
        self.writes: list[tuple[str, int]] = []

    def set_available(self, variant_id: str, quantity: int) -> None:
        self.writes.append((variant_id, quantity))


def run_check(browser: Browser, flow: SupplierFlow, mock: RunningMock,
              writer: FakeWriter, store: EncryptedSessionStore | None = None) -> None:
    store = store or EncryptedSessionStore(SecretBox(generate_key()), MemoryTextRepository())
    with PlaywrightSupplierSession(browser) as session:
        check_listing(
            session, store, flow, Credentials("shop", "pw"), [PasteFromOutbox(mock)],
            SystemClock(), f"{mock.base_url}/product/1", VARIANT, writer,
            code_timeout=10, poll=0.1,
        )


def test_stock_flip_changes_inventory(browser: Browser, flow: SupplierFlow,
                                      mock_supplier: RunningMock) -> None:
    writer = FakeWriter()
    store = EncryptedSessionStore(SecretBox(generate_key()), MemoryTextRepository())
    run_check(browser, flow, mock_supplier, writer, store)
    mock_supplier.control("stock/1", in_stock=False)
    run_check(browser, flow, mock_supplier, writer, store)
    mock_supplier.control("stock/1", in_stock=True)
    run_check(browser, flow, mock_supplier, writer, store)
    assert writer.writes == [(VARIANT, RESTORE_QUANTITY), (VARIANT, 0), (VARIANT, RESTORE_QUANTITY)]


def test_unknown_reading_never_writes(browser: Browser, flow: SupplierFlow,
                                      mock_supplier: RunningMock) -> None:
    mock_supplier.control("selector", changed=True)
    writer = FakeWriter()
    run_check(browser, flow, mock_supplier, writer)
    assert writer.writes == []


def test_failed_login_never_writes(browser: Browser, flow: SupplierFlow,
                                   mock_supplier: RunningMock) -> None:
    mock_supplier.control("captcha", on=True)
    writer = FakeWriter()
    run_check(browser, flow, mock_supplier, writer)
    assert writer.writes == []


def test_removed_listing_sets_inventory_to_zero(browser: Browser, flow: SupplierFlow,
                                                mock_supplier: RunningMock) -> None:
    writer = FakeWriter()
    mock_supplier.control("remove/1")
    run_check(browser, flow, mock_supplier, writer)
    assert writer.writes == [(VARIANT, 0)]
