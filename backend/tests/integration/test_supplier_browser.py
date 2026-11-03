import json
from collections.abc import Callable, Sequence

import pytest
from playwright.sync_api import Browser

from app.core.clock import SystemClock
from app.core.encryption import SecretBox, generate_key
from app.flows.definition import FlowDefinition
from app.flows.login_codes import CodeSource, PastedCodeSource
from app.flows.page import PageError
from app.flows.playwright_session import PlaywrightSupplierSession, SessionNotOpenError
from app.flows.results import Credentials, LoginResult, Reading, ReadingResult
from app.flows.runner import run_extract, run_login
from app.flows.session_store import EncryptedSessionStore, MemoryTextRepository
from app.mail.codes import MailMessage
from tests.integration.conftest import RunningMock, mock_flow_json

CREDS = Credentials(username="shop", password="pw")
FetchMail = Callable[[], Sequence[MailMessage]]


def fetch_mail(mock: RunningMock) -> FetchMail:
    def fetch() -> Sequence[MailMessage]:
        return [
            MailMessage(m["sender"], m["body"], m["sent_at"])  # type: ignore[arg-type]
            for m in mock.outbox()
        ]

    return fetch


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


class CaptchaAfterPrompt(PasteFromOutbox):
    """The Supplier shows its blocked page once the code is submitted."""

    def poll(self, requested_at: float) -> str | None:
        self.mock.control("captcha", on=True)
        return super().poll(requested_at)


def store() -> EncryptedSessionStore:
    return EncryptedSessionStore(SecretBox(generate_key()), MemoryTextRepository())


def login(
    browser: Browser, flow: FlowDefinition, pasted: CodeSource,
    sessions: EncryptedSessionStore, fetch: FetchMail | None = None,
) -> LoginResult:
    with PlaywrightSupplierSession(browser) as session:
        return run_login(flow, session, sessions, CREDS, pasted, fetch, SystemClock(), poll=0.1)


def test_login_with_an_emailed_code(browser: Browser, flow: FlowDefinition,
                                    mock_supplier: RunningMock) -> None:
    result = login(browser, flow, PastedCodeSource(), store(), fetch_mail(mock_supplier))
    assert result is LoginResult.LOGGED_IN


def test_login_with_a_pasted_code(browser: Browser, flow: FlowDefinition,
                                  mock_supplier: RunningMock) -> None:
    result = login(browser, flow, PasteFromOutbox(mock_supplier), store())
    assert result is LoginResult.LOGGED_IN


def test_wrong_code_is_reported(browser: Browser, flow: FlowDefinition,
                                mock_supplier: RunningMock) -> None:
    result = login(browser, flow, PasteFromOutbox(mock_supplier, "000000"), store())
    assert result is LoginResult.WRONG_CODE


def test_wrong_password_is_bad_credentials(browser: Browser, flow: FlowDefinition,
                                           mock_supplier: RunningMock) -> None:
    with PlaywrightSupplierSession(browser) as session:
        result = run_login(flow, session, store(), Credentials("shop", "nope"),
                           PastedCodeSource(), None, SystemClock(), poll=0.1)
    assert result is LoginResult.BAD_CREDENTIALS


def test_no_code_before_the_timeout_cancels_without_a_failed_attempt(
    browser: Browser, mock_supplier: RunningMock
) -> None:
    data = json.loads(mock_flow_json(mock_supplier.base_url))
    data["nodes"][5]["timeout_s"] = 0.5
    flow = FlowDefinition.model_validate(data)
    assert login(browser, flow, PastedCodeSource(), store()) is LoginResult.CODE_TIMEOUT


def test_captcha_page_is_blocked(browser: Browser, flow: FlowDefinition,
                                 mock_supplier: RunningMock) -> None:
    mock_supplier.control("captcha", on=True)
    assert login(browser, flow, PastedCodeSource(), store()) is LoginResult.BLOCKED


def test_block_page_after_the_code_is_blocked_not_a_wrong_code(
    browser: Browser, flow: FlowDefinition, mock_supplier: RunningMock
) -> None:
    result = login(browser, flow, CaptchaAfterPrompt(mock_supplier), store())
    assert result is LoginResult.BLOCKED


def test_saved_session_is_reused_without_a_new_login(browser: Browser, flow: FlowDefinition,
                                                     mock_supplier: RunningMock) -> None:
    sessions = store()
    login(browser, flow, PasteFromOutbox(mock_supplier), sessions)
    emails_after_first_login = len(mock_supplier.outbox())
    result = login(browser, flow, PastedCodeSource(), sessions)
    assert result is LoginResult.SESSION_REUSED
    assert len(mock_supplier.outbox()) == emails_after_first_login


def test_expired_session_triggers_one_login(browser: Browser, flow: FlowDefinition,
                                            mock_supplier: RunningMock) -> None:
    sessions = store()
    login(browser, flow, PasteFromOutbox(mock_supplier), sessions)
    mock_supplier.state.sessions.clear()
    mock_supplier.state.code = None
    result = login(browser, flow, PasteFromOutbox(mock_supplier), sessions)
    assert result is LoginResult.LOGGED_IN


def test_saved_session_is_stored_encrypted(browser: Browser, flow: FlowDefinition,
                                           mock_supplier: RunningMock) -> None:
    repository = MemoryTextRepository()
    sessions = EncryptedSessionStore(SecretBox(generate_key()), repository)
    login(browser, flow, PasteFromOutbox(mock_supplier), sessions)
    assert repository.get() is not None
    assert "session" not in (repository.get() or "")


def extract(browser: Browser, flow: FlowDefinition, mock: RunningMock) -> Reading:
    with PlaywrightSupplierSession(browser) as session:
        run_login(flow, session, store(), CREDS, PasteFromOutbox(mock), None,
                  SystemClock(), poll=0.1)
        return run_extract(flow, session.page, f"{mock.base_url}/product/1")


def test_extracts_in_stock(browser: Browser, flow: FlowDefinition,
                           mock_supplier: RunningMock) -> None:
    assert extract(browser, flow, mock_supplier).result is ReadingResult.IN_STOCK


def test_extracts_out_of_stock_after_a_flip(browser: Browser, flow: FlowDefinition,
                                            mock_supplier: RunningMock) -> None:
    mock_supplier.control("stock/1", in_stock=False)
    assert extract(browser, flow, mock_supplier).result is ReadingResult.OUT_OF_STOCK


def test_removed_page_is_listing_removed(browser: Browser, flow: FlowDefinition,
                                         mock_supplier: RunningMock) -> None:
    mock_supplier.control("remove/1")
    assert extract(browser, flow, mock_supplier).result is ReadingResult.LISTING_REMOVED


def test_changed_selector_is_unknown_not_an_error(browser: Browser, flow: FlowDefinition,
                                                  mock_supplier: RunningMock) -> None:
    mock_supplier.control("selector", changed=True)
    reading = extract(browser, flow, mock_supplier)
    assert reading.result is ReadingResult.UNKNOWN
    assert reading.error_kind == "flow_failure"


def test_lost_session_is_unknown(browser: Browser, flow: FlowDefinition,
                                 mock_supplier: RunningMock) -> None:
    with PlaywrightSupplierSession(browser) as session:
        run_login(flow, session, store(), CREDS, PasteFromOutbox(mock_supplier), None,
                  SystemClock(), poll=0.1)
        mock_supplier.state.sessions.clear()
        reading = run_extract(flow, session.page, f"{mock_supplier.base_url}/product/1")
    assert reading.result is ReadingResult.UNKNOWN
    assert reading.error_kind == "session_lost"


def test_browser_timeout_surfaces_as_page_error(browser: Browser) -> None:
    with PlaywrightSupplierSession(browser) as session, pytest.raises(PageError):
        session.page.goto("http://127.0.0.1:1/")


def test_session_used_before_it_is_opened_raises_a_specific_error(browser: Browser) -> None:
    with pytest.raises(SessionNotOpenError):
        PlaywrightSupplierSession(browser).storage_state_json()
