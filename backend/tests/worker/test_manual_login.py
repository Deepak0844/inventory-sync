import importlib
from collections.abc import Callable
from datetime import timedelta

from app.db.repos.jobs import JobRepo
from app.db.repos.suppliers import SessionCookiesRepo, SupplierRepo
from app.flows.session_store import EncryptedSessionStore
from app.worker.jobs import run_once
from app.worker.manual_login import handle_manual_login
from tests.worker.conftest import World


def test_manual_login_waits_for_the_marker_then_saves_the_session(
    make_world: Callable[..., World],
) -> None:
    w = make_world(variants=1)
    w.page.visible.discard(".me")
    SupplierRepo(w.session, w.box).update(w.supplier_id, blocked=True, paused=True)
    expires = (w.now() + timedelta(minutes=10)).isoformat()
    jobs = JobRepo(w.session)
    job_id = jobs.enqueue(
        "manual_login", w.supplier_id,
        {"manual_state": "queued", "expires_at": expires}, w.now(), w.now(),
    )
    job = jobs.claim_next(w.now(), kinds={"manual_login"})
    assert job is not None

    original_sleep = w.clock.sleep

    def reveal_after_ready(seconds: float) -> None:
        with w.deps.session_factory() as session:
            status = JobRepo(session).latest("manual_login", w.supplier_id)
            assert status is not None and status.payload["manual_state"] == "ready"
        w.page.visible.add(".me")
        original_sleep(seconds)

    w.clock.sleep = reveal_after_ready  # type: ignore[method-assign]
    with w.deps.session_factory() as session:
        handle_manual_login(w.deps, session, job)

    status = JobRepo(w.session).latest("manual_login", w.supplier_id)
    supplier = SupplierRepo(w.session, w.box).get(w.supplier_id)
    stored = EncryptedSessionStore(
        w.box, SessionCookiesRepo(w.session, w.supplier_id, w.now)
    ).load()
    assert status is not None and status.id == job_id
    assert status.payload["manual_state"] == "succeeded"
    assert stored == '{"cookies": [{"name": "session"}], "origins": []}'
    assert supplier is not None and not supplier.blocked and not supplier.paused


def test_manual_login_expires_without_saving_a_session(
    make_world: Callable[..., World],
) -> None:
    w = make_world(variants=1)
    SessionCookiesRepo(w.session, w.supplier_id, w.now).put(None)
    w.page.visible.discard(".me")
    jobs = JobRepo(w.session)
    jobs.enqueue(
        "manual_login", w.supplier_id,
        {"manual_state": "queued", "expires_at": w.now().isoformat()}, w.now(), w.now(),
    )
    job = jobs.claim_next(w.now(), kinds={"manual_login"})
    assert job is not None
    with w.deps.session_factory() as session:
        handle_manual_login(w.deps, session, job)
    status = JobRepo(w.session).latest("manual_login", w.supplier_id)
    assert status is not None and status.payload["manual_state"] == "expired"
    assert SessionCookiesRepo(w.session, w.supplier_id, w.now).get() is None


def test_cancelled_session_stops_even_if_a_replacement_is_queued(
    make_world: Callable[..., World],
) -> None:
    w = make_world(variants=1)
    w.page.visible.discard(".me")
    expires = (w.now() + timedelta(minutes=10)).isoformat()
    jobs = JobRepo(w.session)
    jobs.enqueue(
        "manual_login", w.supplier_id,
        {"manual_state": "queued", "expires_at": expires}, w.now(), w.now(),
    )
    job = jobs.claim_next(w.now(), kinds={"manual_login"})
    assert job is not None
    original_sleep = w.clock.sleep
    sleeps = 0

    def cancel_then_replace(seconds: float) -> None:
        nonlocal sleeps
        sleeps += 1
        if sleeps == 1:
            with w.deps.session_factory() as session:
                repo = JobRepo(session)
                repo.set_result(job.id, "cancelled")
                repo.enqueue(
                    "manual_login", w.supplier_id,
                    {"manual_state": "queued", "expires_at": expires}, w.now(), w.now(),
                )
            w.page.visible.add(".me")
        original_sleep(seconds)

    w.clock.sleep = cancel_then_replace  # type: ignore[method-assign]
    with w.deps.session_factory() as session:
        handle_manual_login(w.deps, session, job)

    status = jobs.status(job.id)
    assert sleeps == 1
    assert status is not None and status.payload["manual_state"] == "cancelled"


def test_the_manual_worker_claims_only_manual_login(make_world: Callable[..., World]) -> None:
    w = make_world(variants=1)
    expires = (w.now() + timedelta(minutes=10)).isoformat()
    JobRepo(w.session).enqueue(
        "manual_login", w.supplier_id,
        {"manual_state": "queued", "expires_at": expires}, w.now(), w.now(),
    )
    manual_worker = importlib.import_module("app.manual_worker")
    assert run_once(w.deps, manual_worker.HANDLERS) is True
    status = JobRepo(w.session).latest("manual_login", w.supplier_id)
    assert status is not None and status.payload["manual_state"] == "succeeded"
