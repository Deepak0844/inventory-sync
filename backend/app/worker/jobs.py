"""Claiming and running jobs, and keeping the loop alive when one fails.

Not responsible for what a job does (the handler modules) or for scheduling.
"""

import logging
import threading
from collections.abc import Callable

from sqlalchemy.orm import Session

from app.core.masking import mask_secrets
from app.db.repos.jobs import JobRecord, JobRepo
from app.db.repos.settings import SettingsRepo
from app.db.repos.suppliers import SupplierRepo
from app.db.repos.test_runs import FlowTestRunRepo
from app.scheduler.tick import tick
from app.worker.approval import handle_apply_approval
from app.worker.check import handle_check_supplier
from app.worker.deps import Deps
from app.worker.login import handle_login
from app.worker.orders import handle_poll_orders
from app.worker.summary import handle_daily_summary
from app.worker.sync import handle_sync_variants
from app.worker.test_run import handle_test_run

log = logging.getLogger(__name__)

Handler = Callable[[Deps, Session, JobRecord], None]
HANDLERS: dict[str, Handler] = {
    "check_supplier": handle_check_supplier,
    "login": handle_login,
    "apply_approval": handle_apply_approval,
    "sync_variants": handle_sync_variants,
    "poll_orders": handle_poll_orders,
    "daily_summary": handle_daily_summary,
    "test_run": handle_test_run,
}
MAX_ATTEMPTS = 3
RETRY_AFTER_S = 300.0
STALE_AFTER_S = 3600.0


def run_once(deps: Deps) -> bool:
    """Claim and run one due job. Returns False when there was none.

    A job that raises is put back for a later retry (and eventually marked
    failed); the worker itself never stops because of it.
    """
    with deps.session_factory() as session:
        job = JobRepo(session).claim_next(deps.now())
    if job is None:
        return False
    with deps.session_factory() as session:
        try:
            handler = HANDLERS.get(job.kind)
            if handler is None:
                raise LookupError(f"no handler for job kind {job.kind!r}")
            handler(deps, session, job)
        except Exception as exc:
            session.rollback()
            error = mask_secrets(f"{type(exc).__name__}: {exc}", _secrets(deps, session, job))
            log.error("job %s (%s) failed: %s", job.id, job.kind, error[:500])
            JobRepo(session).fail(job.id, deps.now(), error[:500], RETRY_AFTER_S, MAX_ATTEMPTS)
        else:
            JobRepo(session).complete(job.id)
    return True


def _secrets(deps: Deps, session: Session, job: JobRecord) -> list[str]:
    """Secrets that must never reach the job's stored error or the log."""
    found: list[str] = []
    try:
        secrets = SettingsRepo(session, deps.box).get_secrets()
        found += [secrets.client_secret or "", secrets.mailbox_password or ""]
        if job.supplier_id is not None:
            credentials = SupplierRepo(session, deps.box).get_credentials(job.supplier_id)
            found += [credentials.password] if credentials else []
    except Exception:  # masking is best effort; never let it hide the original failure
        log.warning("could not load secrets to mask", exc_info=True)
    return found


def serve(
    deps: Deps, stop: threading.Event, tick_every_s: float = 30.0, idle_s: float = 1.0
) -> None:
    """Run until `stop` is set: each tick requeues stale jobs and runs the scheduler, then work."""
    next_tick = 0.0
    while not stop.is_set():
        if deps.clock.now() >= next_tick:
            with deps.session_factory() as session:
                # Every tick, not just at start: a job a dead worker left running would
                # otherwise block its Supplier's next check until a restart.
                JobRepo(session).requeue_stale(deps.now(), STALE_AFTER_S)
                FlowTestRunRepo(session).reap_stale(deps.now())  # a dead worker's Test run
                tick(session, deps.box, deps.now())
            next_tick = deps.clock.now() + tick_every_s
        if not run_once(deps):
            stop.wait(idle_s)
