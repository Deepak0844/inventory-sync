from typing import Any

from app.core.encryption import SecretBox, generate_key
from app.flows.definition import FlowDefinition
from app.flows.login_codes import PastedCodeSource
from app.flows.nodes import FlowNode
from app.flows.results import Credentials, LoginResult, ReadingResult
from app.flows.runner import run_extract, run_login
from app.flows.session_store import EncryptedSessionStore, MemoryTextRepository
from tests.fakes import BrokenPage, FakeBrowserSession, FakeClock, ScriptedPage, sample_flow_dict

CREDS = Credentials("owner", "s3cret")


class Recorder:
    def __init__(self) -> None:
        self.seen: list[tuple[str, str | None]] = []

    def after_node(self, node: FlowNode, error: str | None) -> None:
        self.seen.append((node.id, error))


def two_factor_page(code_ok: bool = True) -> ScriptedPage:
    page = ScriptedPage()
    page.on_click["button"] = lambda: page.visible.add("#otp")
    if code_ok:
        page.on_click["#verify"] = lambda: page.visible.add(".me")
    return page


def login(page: ScriptedPage, *, observer: Recorder | None = None, stop_after: str | None = None,
          use_saved_session: bool = True, saved: bool = False, mutate: Any = None) -> LoginResult:
    data = sample_flow_dict()
    if mutate:
        mutate(data)
    flow = FlowDefinition.model_validate(data)
    store = EncryptedSessionStore(SecretBox(generate_key()), MemoryTextRepository())
    if saved:
        store.save("[]")
    pasted = PastedCodeSource()
    pasted.submit("123456")
    return run_login(flow, FakeBrowserSession(page), store, CREDS, pasted, None, FakeClock(),
                     poll=1.0, observer=observer, stop_after=stop_after,
                     use_saved_session=use_saved_session)


def test_observer_hears_about_every_node_in_order() -> None:
    rec = Recorder()
    assert login(two_factor_page(), observer=rec) is LoginResult.LOGGED_IN
    assert [n for n, _ in rec.seen] == [f"n{i}" for i in range(1, 11)]
    assert all(error is None for _, error in rec.seen)


def test_observer_hears_the_error_of_the_node_that_failed() -> None:
    rec = Recorder()
    assert login(two_factor_page(code_ok=False), observer=rec) is LoginResult.WRONG_CODE
    assert rec.seen[-1][0] == "n9"
    assert rec.seen[-1][1]  # a message, not None
    assert "s3cret" not in str(rec.seen) and "123456" not in str(rec.seen)


def test_observer_hears_a_block_page() -> None:
    rec = Recorder()
    page = ScriptedPage(html="CAPTCHA please")
    assert login(page, observer=rec) is LoginResult.BLOCKED
    assert rec.seen == [("n1", "blocked page")]


def test_observer_hears_a_browser_error() -> None:
    rec = Recorder()
    assert login(BrokenPage(), observer=rec) is LoginResult.BROWSER_ERROR
    assert rec.seen[0][0] == "n1" and rec.seen[0][1]


def test_stop_after_ends_the_walk_at_that_node() -> None:
    rec = Recorder()
    page = two_factor_page()
    assert login(page, observer=rec, stop_after="n4") is LoginResult.LOGGED_IN
    assert [n for n, _ in rec.seen] == ["n1", "n2", "n3", "n4"]
    assert page.filled == {"#email": "owner", "#password": "s3cret"}


def test_the_saved_session_can_be_ignored_so_every_node_runs() -> None:
    rec = Recorder()
    page = two_factor_page()
    page.visible.add(".me")
    result = login(page, observer=rec, saved=True, use_saved_session=False)
    assert result is LoginResult.LOGGED_IN
    assert len(rec.seen) == 10


def test_the_saved_session_is_used_by_default() -> None:
    rec = Recorder()
    page = ScriptedPage(visible={".me"})
    assert login(page, observer=rec, saved=True) is LoginResult.SESSION_REUSED
    assert rec.seen == []


def read(page: ScriptedPage) -> Any:
    return run_extract(FlowDefinition.model_validate(sample_flow_dict()), page,
                       "http://supplier.test/p/1")


def test_reading_says_which_rule_matched() -> None:
    assert read(ScriptedPage(visible={"#stock"}, texts={"#stock": "In stock"})
                ).matched_rule == "in_stock_if"
    assert read(ScriptedPage(visible={"#stock"}, texts={"#stock": "Out of stock"})
                ).matched_rule == "out_of_stock_if"


def test_reading_without_a_match_has_no_rule() -> None:
    reading = read(ScriptedPage(visible={"#stock"}, texts={"#stock": "Soon"}))
    assert reading.result is ReadingResult.UNKNOWN and reading.matched_rule is None


def test_scripted_page_screenshot_records_the_masks() -> None:
    page = ScriptedPage()
    assert page.screenshot(["#password"]) == b"png"
    assert page.screenshots == [["#password"]]
