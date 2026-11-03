from collections.abc import Callable
from contextlib import nullcontext
from datetime import timedelta

from app.db.repos.codes import PastedCodeRepo
from app.db.repos.jobs import JobRecord
from app.db.repos.notifications import NotificationRepo
from app.db.repos.suppliers import SessionCookiesRepo, SupplierRepo
from app.flows.page import PageResponse
from app.mail.codes import MailMessage
from app.worker.check import handle_check_supplier
from app.worker.deps import BrowserFactory
from app.worker.login import DbPastedCodeSource
from tests.fakes import FakeBrowserSession, ScriptedPage
from tests.worker.conftest import T0, World

RIGHT = "111111"


class LoginSite(ScriptedPage):
    """Password page, then a code box, then the account menu for the right code."""

    def __init__(self, password_ok: bool = True, blocked: bool = False) -> None:
        super().__init__()
        self.on_click["button"] = self._password
        self.on_click["#verify"] = self._code
        self.password_ok, self.blocked = password_ok, blocked
        self.stock = {"#stock": "In stock"}

    def _password(self) -> None:
        if self.blocked:
            self.html = "Please complete the CAPTCHA"
        elif self.password_ok:
            self.visible.add("#otp")

    def _code(self) -> None:
        if self.filled.get("#otp") == RIGHT:
            self.visible.add(".me")

    def goto(self, url: str) -> PageResponse | None:
        if "/p/" in url:
            self.visible.add("#stock")
            self.texts["#stock"] = "In stock"
        return super().goto(url)


def logged_out_world(make_world: Callable[..., World], page: ScriptedPage, **fields: object
                     ) -> World:
    w = make_world(variants=1, **fields)
    SessionCookiesRepo(w.session, w.supplier_id, w.now).put(None)
    w.page.__dict__.update(page.__dict__)  # share state with the scripted login site
    w.deps.browser = _browser_for(page)
    return w


def _browser_for(page: ScriptedPage) -> BrowserFactory:
    return lambda: nullcontext(FakeBrowserSession(page))


def run(w: World) -> None:
    with w.deps.session_factory() as session:
        handle_check_supplier(w.deps, session, JobRecord(1, "check_supplier", w.supplier_id, {}, 0))


def supplier(w: World):  # type: ignore[no-untyped-def]
    return SupplierRepo(w.session, w.box).get(w.supplier_id)


def kinds(w: World) -> list[str]:
    return [n.kind for n in NotificationRepo(w.session).list(resolved=False)]


def test_a_pasted_code_logs_in_and_the_check_continues(make_world: Callable[..., World]) -> None:
    page = LoginSite()
    w = logged_out_world(make_world, page)
    PastedCodeRepo(w.session, w.box).submit(w.supplier_id, RIGHT, w.now())
    run(w)
    assert w.shopify.writes == [(w.gids[0], 100)]
    assert supplier(w).waiting_for_code_until is None


def test_a_wrong_code_twice_pauses_the_supplier(make_world: Callable[..., World]) -> None:
    w = logged_out_world(make_world, LoginSite(), two_fa_methods=["ui_code", "email_code"])
    w.mail.append(MailMessage("no-reply@supplier.test", "code 000000", T0 + 1))
    run(w)
    s = supplier(w)
    assert s.paused and s.failed_login_attempts == 2 and "twice" in (s.pause_reason or "")
    assert "login_attention" in kinds(w) and w.shopify.writes == []


def test_a_wrong_password_pauses_at_once(make_world: Callable[..., World]) -> None:
    w = logged_out_world(make_world, LoginSite(password_ok=False))
    run(w)
    assert supplier(w).paused and "password" in (supplier(w).pause_reason or "")


def test_no_code_in_time_cancels_without_a_failed_attempt(make_world: Callable[..., World]
                                                         ) -> None:
    w = logged_out_world(make_world, LoginSite())
    run(w)
    s = supplier(w)
    assert not s.paused and s.failed_login_attempts == 0 and s.waiting_for_code_until is None
    assert "needs_code" in kinds(w) and w.shopify.writes == []


def test_a_code_pasted_before_the_run_started_is_ignored(make_world: Callable[..., World]
                                                        ) -> None:
    w = logged_out_world(make_world, LoginSite())
    PastedCodeRepo(w.session, w.box).submit(w.supplier_id, RIGHT, w.now() - timedelta(hours=1))
    run(w)
    assert "needs_code" in kinds(w) and w.shopify.writes == []


def test_a_blocked_login_marks_the_supplier_and_changes_nothing(make_world: Callable[..., World]
                                                               ) -> None:
    w = logged_out_world(make_world, LoginSite(blocked=True))
    run(w)
    assert supplier(w).blocked and "blocked" in kinds(w) and w.shopify.writes == []


def test_the_prompt_is_shown_while_waiting_and_cleared_after(make_world: Callable[..., World]
                                                            ) -> None:
    w = make_world(variants=1, code_window_min=10)
    with w.deps.session_factory() as session:
        source = DbPastedCodeSource(w.deps, session, supplier(w))
        assert source.poll(T0) is None
        assert supplier(w).waiting_for_code_until == w.now() + timedelta(minutes=10)
        source.stop_waiting()
        assert supplier(w).waiting_for_code_until is None


def test_a_login_problem_notifies_only_once(make_world: Callable[..., World]) -> None:
    w = logged_out_world(make_world, LoginSite())
    run(w)
    SupplierRepo(w.session, w.box).update(w.supplier_id, paused=False)
    run(w)
    assert kinds(w).count("needs_code") == 1
