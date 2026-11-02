from collections.abc import Sequence

from playwright.sync_api import Browser

from app.core.clock import SystemClock
from app.core.encryption import SecretBox, generate_key
from app.flows.extract import Reading, ReadingResult, extract_stock
from app.flows.login import Credentials, LoginResult, ensure_logged_in
from app.flows.login_codes import CodeSource, MailboxCodeSource, PastedCodeSource
from app.flows.playwright_session import PlaywrightSupplierSession
from app.flows.session_store import EncryptedSessionStore, MemoryTextRepository
from app.flows.supplier_flow import SupplierFlow
from app.mail.codes import MailMessage
from tests.integration.conftest import RunningMock

CREDS = Credentials(username="shop", password="pw")


def mailbox(mock: RunningMock, flow: SupplierFlow) -> MailboxCodeSource:
    def fetch() -> Sequence[MailMessage]:
        return [
            MailMessage(m["sender"], m["body"], m["sent_at"])  # type: ignore[arg-type]
            for m in mock.outbox()
        ]

    return MailboxCodeSource(fetch, flow.mail_sender, flow.mail_code_pattern)


class PasteFromOutbox:
    """Stands in for the owner reading their email and pasting the code."""

    def __init__(self, mock: RunningMock, paste: str | None = None) -> None:
        self.mock = mock
        self.paste = paste

    def poll(self, requested_at: float) -> str | None:
        if self.paste is not None:
            return self.paste
        outbox = self.mock.outbox()
        return str(outbox[-1]["body"]).rsplit(" ", 1)[1] if outbox else None


def store() -> EncryptedSessionStore:
    return EncryptedSessionStore(SecretBox(generate_key()), MemoryTextRepository())


def run_login(
    browser: Browser, flow: SupplierFlow, sources: Sequence[CodeSource],
    sessions: EncryptedSessionStore, timeout: float = 10,
) -> LoginResult:
    with PlaywrightSupplierSession(browser) as session:
        return ensure_logged_in(
            session, sessions, flow, CREDS, sources, SystemClock(), code_timeout=timeout, poll=0.1
        )


def test_login_with_an_emailed_code(browser: Browser, flow: SupplierFlow,
                                    mock_supplier: RunningMock) -> None:
    result = run_login(browser, flow, [mailbox(mock_supplier, flow)], store())
    assert result is LoginResult.LOGGED_IN


def test_login_with_a_pasted_code(browser: Browser, flow: SupplierFlow,
                                  mock_supplier: RunningMock) -> None:
    result = run_login(browser, flow, [PasteFromOutbox(mock_supplier)], store())
    assert result is LoginResult.LOGGED_IN


def test_wrong_code_is_reported(browser: Browser, flow: SupplierFlow,
                                mock_supplier: RunningMock) -> None:
    result = run_login(browser, flow, [PasteFromOutbox(mock_supplier, "000000")], store())
    assert result is LoginResult.WRONG_CODE


def test_no_code_before_the_timeout_cancels_without_a_failed_attempt(
    browser: Browser, flow: SupplierFlow
) -> None:
    result = run_login(browser, flow, [PastedCodeSource()], store(), timeout=0.5)
    assert result is LoginResult.CODE_TIMEOUT


def test_captcha_page_is_blocked(browser: Browser, flow: SupplierFlow,
                                 mock_supplier: RunningMock) -> None:
    mock_supplier.control("captcha", on=True)
    assert run_login(browser, flow, [], store()) is LoginResult.BLOCKED


def test_saved_session_is_reused_without_a_new_login(browser: Browser, flow: SupplierFlow,
                                                     mock_supplier: RunningMock) -> None:
    sessions = store()
    run_login(browser, flow, [PasteFromOutbox(mock_supplier)], sessions)
    emails_after_first_login = len(mock_supplier.outbox())
    result = run_login(browser, flow, [], sessions)
    assert result is LoginResult.SESSION_REUSED
    assert len(mock_supplier.outbox()) == emails_after_first_login


def test_expired_session_triggers_one_login(browser: Browser, flow: SupplierFlow,
                                            mock_supplier: RunningMock) -> None:
    sessions = store()
    run_login(browser, flow, [PasteFromOutbox(mock_supplier)], sessions)
    mock_supplier.state.sessions.clear()
    mock_supplier.state.code = None
    result = run_login(browser, flow, [PasteFromOutbox(mock_supplier)], sessions)
    assert result is LoginResult.LOGGED_IN


def test_saved_session_is_stored_encrypted(browser: Browser, flow: SupplierFlow,
                                           mock_supplier: RunningMock) -> None:
    repository = MemoryTextRepository()
    sessions = EncryptedSessionStore(SecretBox(generate_key()), repository)
    run_login(browser, flow, [PasteFromOutbox(mock_supplier)], sessions)
    assert repository.get() is not None
    assert "session" not in (repository.get() or "")


def extract(
    browser: Browser, flow: SupplierFlow, mock: RunningMock, path: str = "/product/1"
) -> Reading:
    sessions = store()
    with PlaywrightSupplierSession(browser) as session:
        ensure_logged_in(session, sessions, flow, CREDS, [PasteFromOutbox(mock)],
                         SystemClock(), code_timeout=10, poll=0.1)
        return extract_stock(session.page, flow, f"{mock.base_url}{path}")


def test_extracts_in_stock(browser: Browser, flow: SupplierFlow,
                           mock_supplier: RunningMock) -> None:
    assert extract(browser, flow, mock_supplier).result is ReadingResult.IN_STOCK


def test_extracts_out_of_stock_after_a_flip(browser: Browser, flow: SupplierFlow,
                                            mock_supplier: RunningMock) -> None:
    mock_supplier.control("stock/1", in_stock=False)
    assert extract(browser, flow, mock_supplier).result is ReadingResult.OUT_OF_STOCK


def test_removed_page_is_listing_removed(browser: Browser, flow: SupplierFlow,
                                         mock_supplier: RunningMock) -> None:
    mock_supplier.control("remove/1")
    assert extract(browser, flow, mock_supplier).result is ReadingResult.LISTING_REMOVED


def test_changed_selector_is_unknown_not_an_error(browser: Browser, flow: SupplierFlow,
                                                  mock_supplier: RunningMock) -> None:
    mock_supplier.control("selector", changed=True)
    reading = extract(browser, flow, mock_supplier)
    assert reading.result is ReadingResult.UNKNOWN
    assert reading.error_kind == "flow_failure"


def test_lost_session_is_unknown(browser: Browser, flow: SupplierFlow,
                                 mock_supplier: RunningMock) -> None:
    sessions = store()
    with PlaywrightSupplierSession(browser) as session:
        ensure_logged_in(session, sessions, flow, CREDS, [PasteFromOutbox(mock_supplier)],
                         SystemClock(), code_timeout=10, poll=0.1)
        mock_supplier.state.sessions.clear()
        reading = extract_stock(session.page, flow, f"{mock_supplier.base_url}/product/1")
    assert reading.result is ReadingResult.UNKNOWN
    assert reading.error_kind == "session_lost"


