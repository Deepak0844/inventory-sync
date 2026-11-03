"""A person logs in to a Supplier in an ordinary browser; the worker then saves the session.

The browser is a plain Chromium process, not one driven by Playwright, because a driven browser
is marked as automated and a Supplier's CAPTCHA can then reject a correct answer. The price is
that the worker cannot watch the page: the owner says "Done" (or closes the window), and only
then does the worker open the same profile headless to check the logged-in marker and read the
cookies. Not responsible for scheduled checks, which only reuse the saved session.
"""

import json
import shutil
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.encryption import DecryptionError
from app.db.repos.jobs import JobRecord, JobRepo
from app.db.repos.suppliers import SessionCookiesRepo, SupplierRecord, SupplierRepo
from app.flows.definition import FlowDefinition
from app.flows.page import PageError
from app.flows.session_store import EncryptedSessionStore
from app.worker.deps import Deps

NOT_LOGGED_IN = (
    "Not logged in: the account page did not show you as signed in. "
    "Start again and press Done only after the login has finished."
)


def handle_manual_login(deps: Deps, session: Session, job: JobRecord) -> None:
    """Open a browser for the owner, wait for Done, then check the profile and save the session.

    The outcome is written to the job: `succeeded`, `failed` (with the reason), `expired` or
    `cancelled`. A failed check never replaces a session that was already saved.
    """
    if job.supplier_id is None:
        return
    jobs = JobRepo(session)
    suppliers = SupplierRepo(session, deps.box)
    supplier = suppliers.get(job.supplier_id)
    raw_flow = suppliers.get_flow(job.supplier_id) or suppliers.get_flow_draft(job.supplier_id)
    if supplier is None or raw_flow is None:
        jobs.set_result(job.id, "failed", error="Supplier or complete flow is missing")
        return
    try:
        flow = FlowDefinition.validate_for_manual_login(raw_flow)
    except (ValidationError, ValueError) as exc:
        jobs.set_result(job.id, "failed", error=str(exc))
        return
    if deps.manual_browser is None or deps.profile_browser is None:
        jobs.set_result(job.id, "failed", error="This worker has no manual browser set up")
        return
    # The profile holds the Supplier's cookies unencrypted, so it is always fresh and never kept.
    profile_dir = deps.data_dir / "manual-profiles" / str(supplier.id)
    shutil.rmtree(profile_dir, ignore_errors=True)
    try:
        profile_dir.mkdir(parents=True)
        if _wait_for_owner(deps, jobs, job, supplier, flow, profile_dir):
            _save_if_logged_in(deps, session, jobs, job, supplier, flow, profile_dir)
    except (DecryptionError, PageError, ValueError, OSError) as exc:
        jobs.set_result(job.id, "failed", error=_with_cause(exc))
    finally:
        shutil.rmtree(profile_dir, ignore_errors=True)


def _wait_for_owner(
    deps: Deps, jobs: JobRepo, job: JobRecord, supplier: SupplierRecord,
    flow: FlowDefinition, profile_dir: Path,
) -> bool:
    """Keep the browser open until the owner finishes. True when they did.

    Returns False after recording `cancelled` was seen or `expired`; the browser is closed
    either way when this returns.
    """
    assert deps.manual_browser is not None
    expires_at = datetime.fromisoformat(str(job.payload["expires_at"]))
    with deps.manual_browser(profile_dir, urljoin(supplier.site_url, flow.login_path)) as browser:
        jobs.set_result(job.id, "ready")
        while True:
            current = jobs.status(job.id)
            if current is None or current.payload.get("manual_state") == "cancelled":
                return False
            if current.payload.get("manual_state") == "finishing" or not browser.is_running():
                return True
            if deps.now() >= expires_at:
                jobs.set_result(job.id, "expired")
                return False
            deps.clock.sleep(deps.poll_s)


def _save_if_logged_in(
    deps: Deps, session: Session, jobs: JobRepo, job: JobRecord, supplier: SupplierRecord,
    flow: FlowDefinition, profile_dir: Path,
) -> None:
    assert deps.profile_browser is not None
    jobs.set_result(job.id, "verifying")
    with deps.profile_browser(profile_dir) as browser:
        browser.page.goto(flow.logged_in_url)
        state = _supplier_cookies_only(browser.storage_state_json(), supplier.site_url)
        if not browser.page.is_visible(flow.logged_in_marker):
            count = len(json.loads(state)["cookies"])
            # The page and cookie count tell a wrong logged-in URL from a login that did not stick.
            detail = (f"Opened {browser.page.url or flow.logged_in_url} with {count} "
                      f"cookie{'' if count == 1 else 's'} from the browser.")
            jobs.set_result(job.id, "failed", error=f"{NOT_LOGGED_IN} {detail}")
            return
    EncryptedSessionStore(
        deps.box, SessionCookiesRepo(session, supplier.id, deps.now)).save(state)
    SupplierRepo(session, deps.box).update(
        supplier.id, blocked=False, paused=False, pause_reason=None, failed_login_attempts=0)
    jobs.set_result(job.id, "succeeded")


def _supplier_cookies_only(state_json: str, site_url: str) -> str:
    """Drop cookies that belong to other sites.

    The browser makes background requests of its own, so the profile also holds cookies for
    sites that are not the Supplier. They are not part of the login and are not stored with it.
    """
    host = (urlparse(site_url).hostname or "").lower()
    state = json.loads(state_json)

    def is_supplier(domain: str) -> bool:
        d = domain.lstrip(".").lower()
        return host == d or host.endswith("." + d) or d.endswith("." + host)

    state["cookies"] = [c for c in state["cookies"] if is_supplier(str(c["domain"]))]
    return json.dumps(state)


def _with_cause(exc: BaseException) -> str:
    """The error plus the first line of what caused it.

    `PageError` only says which step failed ("could not open the browser profile"). The
    browser's own reason (profile locked, page closed) is what tells the owner what to fix.
    """
    cause = exc.__cause__
    if cause is None:
        return str(exc)
    return f"{exc}: {str(cause).splitlines()[0][:200] if str(cause) else type(cause).__name__}"
