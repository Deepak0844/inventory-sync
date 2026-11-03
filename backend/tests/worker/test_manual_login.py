"""Manual login: a person logs in with a plain browser, then the worker checks the profile."""

import importlib
import json
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

from app.db.repos.jobs import JobRecord, JobRepo
from app.db.repos.suppliers import SessionCookiesRepo, SupplierRepo
from app.flows.page import PageError
from app.flows.session_store import EncryptedSessionStore
from app.worker.jobs import run_once
from app.worker.manual_login import handle_manual_login
from tests.worker.conftest import BASE, World

LOGIN_URL = f"{BASE}/login"


def start(w: World, minutes: int = 10) -> JobRecord:
    jobs = JobRepo(w.session)
    expires = (w.now() + timedelta(minutes=minutes)).isoformat()
    jobs.enqueue("manual_login", w.supplier_id,
                 {"manual_state": "queued", "expires_at": expires}, w.now(), w.now())
    job = jobs.claim_next(w.now(), kinds={"manual_login"})
    assert job is not None
    return job


def run(w: World, job: JobRecord, on_sleep: Callable[[int], None] | None = None) -> None:
    """Run the handler; `on_sleep(n)` is the owner doing something on the n-th wait."""
    original, waits = w.clock.sleep, 0

    def sleep(seconds: float) -> None:
        nonlocal waits
        waits += 1
        if on_sleep is not None:
            on_sleep(waits)
        original(seconds)

    w.clock.sleep = sleep  # type: ignore[method-assign]
    with w.deps.session_factory() as session:
        handle_manual_login(w.deps, session, job)


def ask(w: World, job: JobRecord, state: str) -> None:
    """What the dashboard does: Done sets "finishing", Cancel sets "cancelled"."""
    with w.deps.session_factory() as session:
        JobRepo(session).set_result(job.id, state)


def outcome(w: World) -> tuple[str, str | None]:
    status = JobRepo(w.session).latest("manual_login", w.supplier_id)
    assert status is not None
    return str(status.payload["manual_state"]), status.payload.get("error")


def saved(w: World) -> str | None:
    return EncryptedSessionStore(
        w.box, SessionCookiesRepo(w.session, w.supplier_id, w.now)).load()


def test_done_closes_the_browser_then_checks_the_profile_and_saves_the_session(
    make_world: Callable[..., World],
) -> None:
    w = make_world(variants=1)
    SessionCookiesRepo(w.session, w.supplier_id, w.now).put(None)
    SupplierRepo(w.session, w.box).update(w.supplier_id, blocked=True, paused=True)
    w.manual.stays_open = True
    job = start(w)
    states: list[str] = []

    def owner(wait: int) -> None:
        states.append(outcome(w)[0])
        ask(w, job, "finishing")

    run(w, job, owner)
    supplier = SupplierRepo(w.session, w.box).get(w.supplier_id)
    assert states == ["ready"]
    assert w.manual.launched[0][1] == LOGIN_URL
    assert w.events == ["browser started", "browser stopped", "profile opened"]
    assert outcome(w) == ("succeeded", None)
    assert saved(w) == (
        '{"cookies": [{"name": "session", "value": "x", "domain": ".supplier.test"}], '
        '"origins": []}')
    assert supplier is not None and not supplier.blocked and not supplier.paused


def test_closing_the_browser_window_counts_as_done(make_world: Callable[..., World]) -> None:
    w = make_world(variants=1)
    SessionCookiesRepo(w.session, w.supplier_id, w.now).put(None)
    run(w, start(w))  # the fake browser is already closed on the first look
    assert outcome(w) == ("succeeded", None)
    assert saved(w) is not None


def test_done_before_logging_in_keeps_the_old_session_and_says_so(
    make_world: Callable[..., World],
) -> None:
    w = make_world(variants=1)
    old = saved(w)
    w.page.visible.discard(".me")
    run(w, start(w))
    state, error = outcome(w)
    assert state == "failed" and error is not None and "not logged in" in error.lower()
    assert saved(w) == old


def test_a_browser_error_while_checking_the_profile_records_why(
    make_world: Callable[..., World],
) -> None:
    w = make_world(variants=1)
    w.profile.error = PageError("could not open the profile")
    w.profile.error.__cause__ = RuntimeError("profile is locked by another process")
    run(w, start(w))
    state, error = outcome(w)
    assert state == "failed"
    assert error is not None and "could not open the profile" in error
    assert "profile is locked" in error


def test_a_session_that_expires_is_closed_and_never_checked(
    make_world: Callable[..., World],
) -> None:
    w = make_world(variants=1)
    w.manual.stays_open = True
    run(w, start(w, minutes=0))
    assert outcome(w)[0] == "expired"
    assert w.events == ["browser started", "browser stopped"]


def test_cancel_closes_the_browser_and_never_checks_the_profile(
    make_world: Callable[..., World],
) -> None:
    w = make_world(variants=1)
    w.manual.stays_open = True
    job = start(w)
    run(w, job, lambda wait: ask(w, job, "cancelled"))
    assert outcome(w)[0] == "cancelled"
    assert w.events == ["browser started", "browser stopped"]


def test_cancelled_session_stops_even_if_a_replacement_is_queued(
    make_world: Callable[..., World],
) -> None:
    w = make_world(variants=1)
    w.manual.stays_open = True
    job = start(w)

    def cancel_then_replace(wait: int) -> None:
        with w.deps.session_factory() as session:
            repo = JobRepo(session)
            repo.set_result(job.id, "cancelled")
            repo.enqueue("manual_login", w.supplier_id,
                         {"manual_state": "queued", "expires_at": w.now().isoformat()},
                         w.now(), w.now())

    run(w, job, cancel_then_replace)
    status = JobRepo(w.session).status(job.id)
    assert status is not None and status.payload["manual_state"] == "cancelled"
    assert w.events == ["browser started", "browser stopped"]


def test_the_profile_folder_is_fresh_and_deleted_afterwards(
    make_world: Callable[..., World], tmp_path: Path,
) -> None:
    w = make_world(variants=1)
    stale = tmp_path / "manual-profiles" / str(w.supplier_id)
    stale.mkdir(parents=True)
    (stale / "Cookies").write_text("left over from an earlier login")
    run(w, start(w))
    profile_dir, _ = w.manual.launched[0]
    assert profile_dir == stale and w.manual.profile_existed == [True]
    assert not stale.exists()


def test_a_worker_without_the_manual_browser_fails_the_job_clearly(
    make_world: Callable[..., World],
) -> None:
    w = make_world(variants=1)
    w.deps.manual_browser = None
    run(w, start(w))
    state, error = outcome(w)
    assert state == "failed" and error is not None and "manual browser" in error


def test_the_manual_worker_claims_only_manual_login(make_world: Callable[..., World]) -> None:
    w = make_world(variants=1)
    expires = (w.now() + timedelta(minutes=10)).isoformat()
    JobRepo(w.session).enqueue(
        "manual_login", w.supplier_id,
        {"manual_state": "queued", "expires_at": expires}, w.now(), w.now(),
    )
    manual_worker = importlib.import_module("app.manual_worker")
    assert run_once(w.deps, manual_worker.HANDLERS) is True
    assert outcome(w)[0] == "succeeded"


def test_only_the_suppliers_own_cookies_are_saved(make_world: Callable[..., World]) -> None:
    """Chromium makes background requests of its own; those sites' cookies are not the login."""
    w = make_world(variants=1)
    SessionCookiesRepo(w.session, w.supplier_id, w.now).put(None)
    w.profile.cookie_domains = [".supplier.test", "supplier.test", "shop.supplier.test",
                                ".google.com", "notsupplier.test"]
    run(w, start(w))
    stored = saved(w)
    assert stored is not None
    domains = [c["domain"] for c in json.loads(stored)["cookies"]]
    assert domains == [".supplier.test", "supplier.test", "shop.supplier.test"]


def test_a_failed_check_says_which_page_it_opened_and_how_many_cookies_it_had(
    make_world: Callable[..., World],
) -> None:
    """So a wrong logged-in URL can be told apart from a login that did not stick."""
    w = make_world(variants=1)
    w.page.visible.discard(".me")
    w.profile.cookie_domains = [".supplier.test", ".google.com"]
    run(w, start(w))
    _, error = outcome(w)
    assert error is not None
    assert "http://supplier.test/account" in error and "1 cookie" in error
