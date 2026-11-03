"""Logging in to a Supplier the way PLAN.md section 4 says, with pauses and notifications.

Not responsible for what happens after login (`app.worker.check`).
"""

from datetime import timedelta

from sqlalchemy.orm import Session

from app.db.repos.codes import PastedCodeRepo
from app.db.repos.jobs import JobRecord
from app.db.repos.runs import RunRepo
from app.db.repos.settings import SettingsRepo
from app.db.repos.suppliers import SessionCookiesRepo, SupplierRecord, SupplierRepo
from app.engine.login_policy import LoginAction, judge_login
from app.flows.definition import FlowDefinition
from app.flows.nodes.login import AwaitCode
from app.flows.page import BrowserSession
from app.flows.results import Credentials, LoginResult
from app.flows.runner import run_login
from app.flows.session_store import EncryptedSessionStore
from app.worker.deps import Deps
from app.worker.notify import notify_once


class DbPastedCodeSource:
    """Codes pasted in the dashboard, read from the database.

    The first poll means the run is now waiting for a code, so it marks the
    Supplier as waiting; that is what makes the "needs code" card appear.
    """

    def __init__(self, deps: Deps, session: Session, supplier: SupplierRecord) -> None:
        self._deps = deps
        self._suppliers = SupplierRepo(session, deps.box)
        self._codes = PastedCodeRepo(session, deps.box)
        self._supplier = supplier
        self._waiting = False

    def poll(self, requested_at: float) -> str | None:
        """Return a pasted code that arrived after the code was requested, else None."""
        if not self._waiting:
            window = timedelta(minutes=self._supplier.code_window_min)
            self._suppliers.update(self._supplier.id,
                                   waiting_for_code_until=self._deps.now() + window)
            self._waiting = True
        pasted = self._codes.take(self._supplier.id)
        if pasted is None or pasted.submitted_at.timestamp() < requested_at:
            return None
        return pasted.code

    def stop_waiting(self) -> None:
        """Clear the waiting mark so the card goes away."""
        if self._waiting:
            self._suppliers.update(self._supplier.id, waiting_for_code_until=None)
            self._waiting = False


def for_supplier(flow: FlowDefinition, supplier: SupplierRecord) -> FlowDefinition:
    """Return a copy of the flow using the Supplier's 2FA methods and code window."""
    flow = flow.model_copy(deep=True)
    for node in flow.nodes:
        if isinstance(node, AwaitCode):
            node.methods = [m for m in node.methods if m in supplier.two_fa_methods]
            node.timeout_s = supplier.code_window_min * 60.0
    return flow


def login_with_policy(
    deps: Deps, session: Session, supplier: SupplierRecord, flow: FlowDefinition,
    credentials: Credentials, browser: BrowserSession, store: EncryptedSessionStore,
) -> LoginAction:
    """Log in, retrying a wrong code once, and act on the outcome.

    Returns DONE when the session is usable. Otherwise the Supplier has been
    paused (PAUSE), the run cancelled with a "needs code" notification (CANCEL),
    or stopped with a notification for the cause (STOP). Readings are Unknown in
    all three, so nothing changes in Shopify.
    """
    suppliers = SupplierRepo(session, deps.box)
    settings = SettingsRepo(session, deps.box)
    fetch_mail = None
    if "email_code" in supplier.two_fa_methods:
        fetch_mail = deps.mail(settings.get(), settings.get_secrets())
    flow = for_supplier(flow, supplier)
    codes = DbPastedCodeSource(deps, session, supplier)
    failed = 0
    while True:
        try:
            result = run_login(flow, browser, store, credentials, codes, fetch_mail,
                               deps.clock, deps.poll_s)
        finally:
            codes.stop_waiting()
        verdict = judge_login(result, failed)
        failed = verdict.failed_attempts
        now = deps.now()
        name = supplier.name
        if verdict.action is LoginAction.DONE:
            suppliers.update(supplier.id, failed_login_attempts=0, blocked=False)
        elif verdict.action is LoginAction.PAUSE:
            reason = ("Wrong username or password" if result is LoginResult.BAD_CREDENTIALS
                      else "Wrong code twice")
            suppliers.update(supplier.id, paused=True, pause_reason=reason,
                             failed_login_attempts=failed)
            notify_once(session, "login_attention", supplier.id,
                        f"{name}: {reason}. Checks are paused until you retry.", now)
        elif verdict.action is LoginAction.CANCEL:
            notify_once(session, "needs_code", supplier.id,
                        f"{name} needed a code and none arrived in time.", now)
        elif verdict.action is LoginAction.STOP:
            _stopped(deps, session, supplier, result)
        if verdict.action is not LoginAction.RETRY:
            return verdict.action


def _stopped(deps: Deps, session: Session, supplier: SupplierRecord, result: LoginResult) -> None:
    now, name = deps.now(), supplier.name
    if result is LoginResult.BLOCKED:
        SupplierRepo(session, deps.box).update(supplier.id, blocked=True)
        notify_once(session, "blocked", supplier.id, f"{name} blocked the login.", now)
    elif result is LoginResult.BROWSER_ERROR:
        notify_once(session, "supplier_unreachable", supplier.id,
                    f"{name} could not be reached.", now)
    else:
        notify_once(session, "flow_failure", supplier.id,
                    f"{name}: the login flow could not be completed.", now)


def handle_login(deps: Deps, session: Session, job: JobRecord) -> None:
    """The Login button: log in now so the session is ready, even for a paused Supplier."""
    suppliers = SupplierRepo(session, deps.box)
    supplier = None if job.supplier_id is None else suppliers.get(job.supplier_id)
    flow_json = None if supplier is None else suppliers.get_flow(supplier.id)
    credentials = None if supplier is None else suppliers.get_credentials(supplier.id)
    if supplier is None:
        return
    if flow_json is None or credentials is None:
        notify_once(session, "flow_failure", supplier.id,
                    f"{supplier.name}: add a flow and credentials before logging in.", deps.now())
        return
    runs = RunRepo(session)
    run_id = runs.start(supplier.id, "login", deps.now())
    store = EncryptedSessionStore(deps.box, SessionCookiesRepo(session, supplier.id, deps.now))
    action = LoginAction.STOP
    try:
        with deps.browser() as browser:
            action = login_with_policy(deps, session, supplier,
                                       FlowDefinition.model_validate(flow_json), credentials,
                                       browser, store)
    finally:
        runs.finish(run_id, "ok" if action is LoginAction.DONE else "stopped", action.value,
                    deps.now())
