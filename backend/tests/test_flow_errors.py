from dataclasses import replace
from typing import Any

import pytest

from app.core.clock import SystemClock
from app.core.encryption import SecretBox, generate_key
from app.flows.extract import ReadingResult, extract_stock
from app.flows.login import Credentials, LoginResult, ensure_logged_in
from app.flows.session_store import EncryptedSessionStore, MemoryTextRepository
from tests.fakes import BrokenPage, FakeBrowserSession, sample_flow


def test_browser_failure_while_reading_is_unknown() -> None:
    reading = extract_stock(BrokenPage(), sample_flow(), "http://supplier.test/p/1")
    assert reading.result is ReadingResult.UNKNOWN
    assert reading.error_kind == "browser_error"


def test_browser_failure_while_logging_in_is_reported_not_raised() -> None:
    store = EncryptedSessionStore(SecretBox(generate_key()), MemoryTextRepository())
    result = ensure_logged_in(
        FakeBrowserSession(BrokenPage()), store, sample_flow(), Credentials("u", "p"), [],
        SystemClock(), code_timeout=1, poll=0.1,
    )
    assert result is LoginResult.BROWSER_ERROR


def test_undecryptable_saved_session_is_discarded_and_login_continues() -> None:
    repository = MemoryTextRepository()
    EncryptedSessionStore(SecretBox(generate_key()), repository).save("[]")
    store = EncryptedSessionStore(SecretBox(generate_key()), repository)  # rotated key
    result = ensure_logged_in(
        FakeBrowserSession(BrokenPage()), store, sample_flow(), Credentials("u", "p"), [],
        SystemClock(), code_timeout=1, poll=0.1,
    )
    assert result is LoginResult.BROWSER_ERROR  # got as far as the login page
    assert repository.get() is None


@pytest.mark.parametrize("field", ["blocked_text", "stock_selector", "logged_in_marker"])
def test_flow_with_an_empty_required_field_is_rejected(field: str) -> None:
    empty: dict[str, Any] = {field: ""}
    with pytest.raises(ValueError, match=field):
        replace(sample_flow(), **empty)
