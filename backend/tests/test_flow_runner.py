from dataclasses import dataclass, field
from typing import Any

import pytest

from app.core.encryption import SecretBox, generate_key
from app.flows.definition import FlowDefinition
from app.flows.login_codes import PastedCodeSource
from app.flows.results import Credentials, LoginResult, Reading, ReadingResult
from app.flows.runner import run_extract, run_login
from app.flows.session_store import EncryptedSessionStore, MemoryTextRepository
from app.mail.codes import MailboxError, MailMessage
from tests.fakes import (
    BrokenPage,
    FakeBrowserSession,
    FakeClock,
    ScriptedPage,
    sample_flow_dict,
)

CREDS = Credentials(username="owner", password="s3cret")


@dataclass
class Setup:
    flow: FlowDefinition
    page: ScriptedPage
    store: EncryptedSessionStore
    pasted: PastedCodeSource = field(default_factory=PastedCodeSource)

    def login(self, fetch_mail: Any = None) -> LoginResult:
        return run_login(self.flow, FakeBrowserSession(self.page), self.store, CREDS,
                         self.pasted, fetch_mail, FakeClock(), poll=1.0)


def setup(page: ScriptedPage | None = None, mutate: Any = None) -> Setup:
    data = sample_flow_dict()
    if mutate:
        mutate(data)
    return Setup(
        FlowDefinition.model_validate(data),
        page or ScriptedPage(),
        EncryptedSessionStore(SecretBox(generate_key()), MemoryTextRepository()),
    )


def two_factor_page(code_ok: bool = True) -> ScriptedPage:
    """Submitting the password shows the code box; the right code shows the account menu."""
    page = ScriptedPage()
    page.on_click["button"] = lambda: page.visible.add("#otp")
    if code_ok:
        page.on_click["#verify"] = lambda: page.visible.add(".me")
    return page


def test_login_fills_templates_from_credentials_and_code() -> None:
    s = setup(two_factor_page())
    s.pasted.submit("123456")
    assert s.login() is LoginResult.LOGGED_IN
    assert s.page.filled == {"#email": "owner", "#password": "s3cret", "#otp": "123456"}


def test_successful_login_saves_the_session_encrypted() -> None:
    s = setup(two_factor_page())
    s.pasted.submit("123456")
    s.login()
    assert s.store.load() == '[{"name": "session"}]'


def test_wrong_code_is_wrong_code() -> None:
    s = setup(two_factor_page(code_ok=False))
    s.pasted.submit("000000")
    assert s.login() is LoginResult.WRONG_CODE
    assert s.store.load() is None


def test_no_code_prompt_means_bad_credentials() -> None:
    assert setup(ScriptedPage()).login() is LoginResult.BAD_CREDENTIALS


def test_no_code_before_the_timeout_is_code_timeout() -> None:
    assert setup(two_factor_page()).login() is LoginResult.CODE_TIMEOUT


def test_block_page_stops_the_flow() -> None:
    page = ScriptedPage(html="Please complete the CAPTCHA")
    assert setup(page).login() is LoginResult.BLOCKED


def test_browser_failure_is_reported_not_raised() -> None:
    assert setup(BrokenPage()).login() is LoginResult.BROWSER_ERROR


def test_saved_session_that_still_works_skips_the_login() -> None:
    page = ScriptedPage(visible={".me"})
    s = setup(page)
    s.store.save("[]")
    assert s.login() is LoginResult.SESSION_REUSED
    assert page.visited == ["http://supplier.test/account"]


def test_saved_session_that_has_expired_is_cleared_and_login_runs() -> None:
    s = setup(two_factor_page())
    s.store.save("[]")
    s.pasted.submit("123456")
    assert s.login() is LoginResult.LOGGED_IN


def test_undecryptable_saved_session_is_discarded() -> None:
    repository = MemoryTextRepository()
    EncryptedSessionStore(SecretBox(generate_key()), repository).save("[]")
    s = setup(two_factor_page())
    s.store = EncryptedSessionStore(SecretBox(generate_key()), repository)
    s.pasted.submit("123456")
    assert s.login() is LoginResult.LOGGED_IN


def test_only_the_configured_code_methods_are_used() -> None:
    def ui_only(d: dict[str, Any]) -> None:
        d["nodes"][5]["methods"] = ["ui_code"]

    mail_checked: list[bool] = []

    def fetch() -> list[MailMessage]:
        mail_checked.append(True)
        return []

    assert setup(two_factor_page(), ui_only).login(fetch) is LoginResult.CODE_TIMEOUT
    assert mail_checked == []


def test_code_from_the_mailbox_is_used() -> None:
    s = setup(two_factor_page())

    def fetch() -> list[MailMessage]:
        return [MailMessage("no-reply@supplier.test", "code 654321", 1e12)]

    assert s.login(fetch) is LoginResult.LOGGED_IN
    assert s.page.filled["#otp"] == "654321"


def test_mailbox_failure_falls_back_to_the_pasted_code() -> None:
    s = setup(two_factor_page())
    s.pasted.submit("123456")

    def down() -> list[MailMessage]:
        raise MailboxError("down")

    assert s.login(down) is LoginResult.LOGGED_IN


def test_branch_follows_the_yes_edge_when_the_element_is_visible() -> None:
    def add_branch(d: dict[str, Any]) -> None:
        d["nodes"] = d["nodes"][:4] + [
            {"id": "b", "type": "branch", "if_visible": "#cookie-banner"},
            {"id": "dismiss", "type": "click", "selector": "#accept"},
            {"id": "skip", "type": "wait_for", "selector": ".me", "role": "logged_in_marker",
             "timeout_s": 0},
            {"id": "save", "type": "save_session"},
        ]
        d["edges"] = [["n1", "n2"], ["n2", "n3"], ["n3", "n4"], ["n4", "b"],
                      ["b", "dismiss", "yes"], ["b", "skip", "no"], ["dismiss", "skip"],
                      ["skip", "save"]]

    page = ScriptedPage(visible={"#cookie-banner", ".me"})
    assert setup(page, add_branch).login() is LoginResult.LOGGED_IN
    assert "#accept" in page.clicked
    quiet = ScriptedPage(visible={".me"})
    assert setup(quiet, add_branch).login() is LoginResult.LOGGED_IN
    assert "#accept" not in quiet.clicked


# --- extraction -----------------------------------------------------------------


def read(page: ScriptedPage) -> Reading:
    return run_extract(setup().flow, page, "http://supplier.test/p/1")


def stock_page(text: str, qty: str | None = None) -> ScriptedPage:
    page = ScriptedPage(visible={"#stock"}, texts={"#stock": text})
    if qty is not None:
        page.visible.add("#qty")
        page.texts["#qty"] = qty
    return page


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("In stock", ReadingResult.IN_STOCK),
        ("  OUT OF STOCK ", ReadingResult.OUT_OF_STOCK),
        ("Back in a week", ReadingResult.UNKNOWN),
    ],
)
def test_stock_text_maps_to_a_reading(text: str, expected: ReadingResult) -> None:
    assert read(stock_page(text)).result is expected


def test_quantity_is_read_when_the_selector_is_present() -> None:
    assert read(stock_page("In stock", "Only 7 left")).quantity == 7


def test_quantity_is_none_when_not_shown() -> None:
    assert read(stock_page("In stock")).quantity is None


def test_404_is_listing_removed() -> None:
    assert read(ScriptedPage(status=404)).result is ReadingResult.LISTING_REMOVED


def test_missing_stock_element_is_unknown_flow_failure() -> None:
    reading = read(ScriptedPage())
    assert (reading.result, reading.error_kind) == (ReadingResult.UNKNOWN, "flow_failure")


def test_login_page_means_the_session_was_lost() -> None:
    reading = read(ScriptedPage(url="http://supplier.test/login?next=/p/1"))
    assert reading.error_kind == "session_lost"


def test_block_page_is_unknown_blocked() -> None:
    assert read(ScriptedPage(html="CAPTCHA")).error_kind == "blocked"


def test_unmatched_text_is_unknown_no_rule_matched() -> None:
    assert read(stock_page("Ships soon")).error_kind == "no_rule_matched"


def test_browser_failure_while_reading_is_unknown() -> None:
    reading = read(BrokenPage())
    assert (reading.result, reading.error_kind) == (ReadingResult.UNKNOWN, "browser_error")




def test_email_only_flow_with_no_mailbox_fails_fast() -> None:
    def email_only(d: dict[str, Any]) -> None:
        d["nodes"][5]["methods"] = ["email_code"]

    s = setup(two_factor_page(), email_only)
    clock = FakeClock()
    result = run_login(s.flow, FakeBrowserSession(s.page), s.store, CREDS, s.pasted, None,
                       clock, poll=1.0)
    assert result is LoginResult.FLOW_FAILURE
    assert clock.now() == 0


def test_await_code_without_an_earlier_click_ignores_older_pasted_codes() -> None:
    def no_click_first(d: dict[str, Any]) -> None:
        d["nodes"][3] = {"id": "n4", "type": "wait_for", "selector": "#otp", "timeout_s": 0}

    clock = FakeClock(start=100.0)
    pasted = PastedCodeSource(FakeClock(start=50.0))
    pasted.submit("111111")  # pasted at t=50, before this run started at t=100
    page = two_factor_page()
    page.visible.add("#otp")
    s = setup(page, no_click_first)
    result = run_login(s.flow, FakeBrowserSession(page), s.store, CREDS, pasted, None,
                       clock, poll=1.0)
    assert result is LoginResult.CODE_TIMEOUT


def test_corrupt_saved_cookies_are_discarded_and_login_continues() -> None:
    class RejectingSession(FakeBrowserSession):
        cleared_flag = False

        def load_cookies_json(self, cookies_json: str) -> None:
            raise ValueError("not json")

        def clear_cookies(self) -> None:
            self.cleared_flag = True

    s = setup(two_factor_page())
    s.store.save("garbage")
    s.pasted.submit("123456")
    session = RejectingSession(s.page)
    result = run_login(s.flow, session, s.store, CREDS, s.pasted, None, FakeClock(), poll=1.0)
    assert result is LoginResult.LOGGED_IN
    assert session.cleared_flag


def test_cookies_of_an_expired_session_are_cleared_before_the_fresh_login() -> None:
    s = setup(two_factor_page())
    s.store.save("[]")
    s.pasted.submit("123456")
    session = FakeBrowserSession(s.page)
    run_login(s.flow, session, s.store, CREDS, s.pasted, None, FakeClock(), poll=1.0)
    assert session.cleared == 1


def test_words_in_scripts_do_not_make_a_page_blocked() -> None:
    # A normal Shopify login page: "captcha" appears in its scripts, not on screen.
    page = two_factor_page()
    page.html = "<script>const y='captcha'</script>"
    page.texts["body"] = "Log in to your account"
    s = setup(page)
    s.pasted.submit("123456")
    assert s.login() is LoginResult.LOGGED_IN


def test_words_in_scripts_do_not_make_a_listing_blocked() -> None:
    page = stock_page("In stock")
    page.html = "<script>const y='captcha'</script>"
    page.texts["body"] = "In stock"
    assert read(page).result is ReadingResult.IN_STOCK


def test_a_visible_block_message_still_blocks_a_listing() -> None:
    page = stock_page("In stock")
    page.texts["body"] = "Please complete the CAPTCHA to continue"
    assert read(page).error_kind == "blocked"
