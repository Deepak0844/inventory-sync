"""A human completes login in the worker's visible browser."""

from datetime import datetime
from urllib.parse import urljoin

from sqlalchemy.orm import Session

from app.core.encryption import DecryptionError
from app.db.repos.jobs import JobRecord, JobRepo
from app.db.repos.suppliers import SessionCookiesRepo, SupplierRepo
from app.flows.definition import FlowDefinition
from app.flows.page import PageError
from app.flows.session_store import EncryptedSessionStore
from app.worker.deps import Deps


def handle_manual_login(deps: Deps, session: Session, job: JobRecord) -> None:
    """Keep a visible browser open until the owner signs in or the window expires."""
    if job.supplier_id is None:
        return
    jobs = JobRepo(session)
    suppliers = SupplierRepo(session, deps.box)
    supplier = suppliers.get(job.supplier_id)
    raw_flow = suppliers.get_flow(job.supplier_id)
    if supplier is None or raw_flow is None:
        jobs.set_result(job.id, "failed", error="Supplier or complete flow is missing")
        return
    flow = FlowDefinition.model_validate(raw_flow)
    expires_at = datetime.fromisoformat(str(job.payload["expires_at"]))
    store = EncryptedSessionStore(
        deps.box, SessionCookiesRepo(session, supplier.id, deps.now)
    )
    try:
        with deps.browser() as browser:
            saved = store.load()
            if saved is not None:
                try:
                    browser.load_storage_state_json(saved)
                except (ValueError, PageError):
                    store.clear()
                    browser.clear_storage_state()
            browser.page.goto(urljoin(supplier.site_url, flow.login_path))
            jobs.set_result(job.id, "ready")
            while True:
                if browser.page.is_visible(flow.logged_in_marker):
                    store.save(browser.storage_state_json())
                    suppliers.update(
                        supplier.id, blocked=False, paused=False, pause_reason=None,
                        failed_login_attempts=0,
                    )
                    jobs.set_result(job.id, "succeeded")
                    return
                current = jobs.latest("manual_login", supplier.id)
                if current is None or current.payload.get("manual_state") == "cancelled":
                    return
                if deps.now() >= expires_at:
                    jobs.set_result(job.id, "expired")
                    return
                deps.clock.sleep(deps.poll_s)
    except (DecryptionError, PageError, ValueError) as exc:
        jobs.set_result(job.id, "failed", error=str(exc))
