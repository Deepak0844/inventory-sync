"""The `test_run` job: run a flow for the flow builder and record what the worker saw.

A Test run never writes to Shopify and never changes stock: it uses no Shopify
client and none of the Listing, Variant, reading, notification or approval
repositories. It also leaves the Supplier's failed-login count and pause alone,
and works on a copy of the saved session. Not responsible for real checks
(`app.worker.check`) or for serving the files (`app.api.test_runs`).
"""

import logging
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.masking import mask_secrets
from app.db.repos.jobs import JobRecord
from app.db.repos.settings import SettingsRepo
from app.db.repos.suppliers import SessionCookiesRepo, SupplierRecord, SupplierRepo
from app.db.repos.test_runs import FlowTestRunRecord, FlowTestRunRepo
from app.flows.definition import FlowDefinition
from app.flows.nodes import FlowNode
from app.flows.nodes.browser import Fill
from app.flows.page import BrowserSession, PageError
from app.flows.results import Credentials, LoginResult
from app.flows.runner import run_extract, run_login
from app.flows.session_store import EncryptedSessionStore, MemoryTextRepository
from app.flows.snapshot import clean_snapshot_html
from app.worker.deps import Deps
from app.worker.login import DbPastedCodeSource, for_supplier

log = logging.getLogger(__name__)

PASSWORD_FIELDS = "input[type=password]"
FINISHED = ("done", "failed")


def file_url(run_id: int, name: str) -> str:
    """The API path that serves one file of a run."""
    return f"/api/test-runs/{run_id}/files/{name}"


def masked_selectors(flow: FlowDefinition) -> list[str]:
    """Selectors painted over in every screenshot: password fields and every secret fill."""
    found = [PASSWORD_FIELDS]
    for node in flow.nodes:
        if isinstance(node, Fill) and (node.mask or "{{code}}" in node.value):
            found.append(node.selector)
    return list(dict.fromkeys(found))


class _Failed(Exception):
    """The run cannot start or finish; the message is shown to the owner."""


class _Recorder:
    """Takes a masked screenshot after each node and stores the step as it happens."""

    def __init__(self, deps: Deps, repo: FlowTestRunRepo, run_id: int, browser: BrowserSession,
                 folder: Path, masks: list[str], stop_after: str | None) -> None:
        self._deps, self._repo, self._run_id = deps, repo, run_id
        self._browser, self._folder, self._masks = browser, folder, masks
        self._stop_after = stop_after
        self._number = 0
        self.stopped_early = False

    def after_node(self, node: FlowNode, error: str | None) -> None:
        """Record one step; a failed screenshot only leaves the step without a picture."""
        self._number += 1
        name = f"step-{self._number}.png"
        shot = file_url(self._run_id, name) if _save_screenshot(
            self._browser, self._folder / name, self._masks) else None
        self._repo.add_step(self._run_id, {
            "node_id": node.id, "type": node.type, "ok": error is None, "error": error,
            "screenshot_url": shot, "at": self._deps.now().isoformat()})
        self.stopped_early = error is None and node.id == self._stop_after


class _WaitingCodes(DbPastedCodeSource):
    """The pasted-code source that also shows the run as waiting for a code."""

    def __init__(self, deps: Deps, session: Session, supplier: SupplierRecord,
                 repo: FlowTestRunRepo, run_id: int) -> None:
        super().__init__(deps, session, supplier)
        self._repo, self._run_id = repo, run_id
        self._announced = False

    def poll(self, requested_at: float) -> str | None:
        """As the parent does, and on the first poll mark the run `waiting_for_code`."""
        code = super().poll(requested_at)
        if not self._announced:
            self._repo.set_state(self._run_id, "waiting_for_code")
            self._announced = True
        return code


def _save_screenshot(browser: BrowserSession, path: Path, masks: list[str]) -> bool:
    try:
        path.write_bytes(browser.page.screenshot(masks))
    except PageError:
        return False
    return True


def _snapshot(browser: BrowserSession, folder: Path, run_id: int, masks: list[str]
              ) -> dict[str, Any] | None:
    """Screenshot plus a cleaned copy of the page, for the selector picker."""
    try:
        html = clean_snapshot_html(browser.page.content())
    except PageError:
        return None
    if not _save_screenshot(browser, folder / "snapshot.png", masks):
        return None
    (folder / "snapshot.html").write_text(html, encoding="utf-8")
    return {"screenshot_url": file_url(run_id, "snapshot.png"),
            "html_url": file_url(run_id, "snapshot.html")}


def handle_test_run(deps: Deps, session: Session, job: JobRecord) -> None:
    """Run the requested Test run and record its steps, snapshot and reading.

    Never raises for a problem with the flow or the Supplier's site: those end
    the run as `failed` with a message. The job is therefore not retried.
    """
    run_id = int(job.payload["test_run_id"])
    repo = FlowTestRunRepo(session)
    run = repo.get(run_id)
    if run is None or run.state in FINISHED:
        return
    repo.start(run_id)
    suppliers = SupplierRepo(session, deps.box)
    supplier = suppliers.get(run.supplier_id)
    credentials = None if supplier is None else suppliers.get_credentials(supplier.id)
    try:
        if supplier is None:
            raise _Failed("That Supplier no longer exists.")
        if credentials is None:
            raise _Failed("Add the Supplier's credentials before a Test run.")
        _execute(deps, session, repo, run, supplier, credentials)
    except _Failed as exc:
        repo.finish(run_id, "failed", deps.now(), error=str(exc))
    except Exception as exc:
        session.rollback()
        secrets = [credentials.password] if credentials else []
        log.warning("test run %s failed: %s", run_id, type(exc).__name__)
        repo.finish(run_id, "failed", deps.now(),
                    error=mask_secrets(f"The Test run stopped unexpectedly ({type(exc).__name__}).",
                                       secrets))


def _flow_for(session: Session, deps: Deps, run: FlowTestRunRecord, supplier: SupplierRecord
              ) -> FlowDefinition:
    draft = run.request.get("flow")
    raw = draft if draft is not None else SupplierRepo(session, deps.box).get_flow(supplier.id)
    if raw is None:
        raise _Failed("This Supplier has no flow yet.")
    try:
        return for_supplier(FlowDefinition.model_validate(raw), supplier)
    except ValidationError as exc:
        raise _Failed("The flow is not valid: " + "; ".join(
            str(e["msg"]) for e in exc.errors())[:300]) from None


def _execute(deps: Deps, session: Session, repo: FlowTestRunRepo, run: FlowTestRunRecord,
             supplier: SupplierRecord, credentials: Credentials) -> None:
    flow = _flow_for(session, deps, run, supplier)
    up_to: str | None = run.request.get("up_to_node_id")
    listing_url: str | None = run.request.get("listing_url")
    if run.mode == "extract" and not listing_url:
        raise _Failed("Give a Listing URL to test the extract step.")
    folder = deps.data_dir / "test-runs" / str(run.id)
    folder.mkdir(parents=True, exist_ok=True)
    masks = masked_selectors(flow)

    # A throwaway copy of the saved session: reused when valid, but nothing is saved back.
    scratch = MemoryTextRepository()
    scratch.put(SessionCookiesRepo(session, supplier.id, deps.now).get())
    store = EncryptedSessionStore(deps.box, scratch)
    settings = SettingsRepo(session, deps.box)
    fetch_mail = None
    if "email_code" in supplier.two_fa_methods:
        fetch_mail = deps.mail(settings.get(), settings.get_secrets())
    codes = _WaitingCodes(deps, session, supplier, repo, run.id)

    with deps.browser() as browser:
        recorder = _Recorder(deps, repo, run.id, browser, folder, masks, up_to)
        try:
            result = run_login(flow, browser, store, credentials, codes, fetch_mail, deps.clock,
                               deps.poll_s, observer=recorder, stop_after=up_to,
                               use_saved_session=up_to is None)
        finally:
            codes.stop_waiting()
        repo.set_state(run.id, "running")
        logged_in = result in (LoginResult.LOGGED_IN, LoginResult.SESSION_REUSED)
        login_result = "stopped_after_node" if recorder.stopped_early else result.value
        reading = None
        if run.mode == "extract" and logged_in and up_to is None and listing_url:
            found = run_extract(flow, browser.page, listing_url)
            reading = {"result": found.result.value, "error_kind": found.error_kind,
                       "quantity": found.quantity, "matched_rule": found.matched_rule}
        snapshot = _snapshot(browser, folder, run.id, masks)
    repo.finish(run.id, "done" if logged_in else "failed", deps.now(), snapshot=snapshot,
                reading=reading, login_result=login_result,
                error=None if logged_in else f"The login ended with {result.value}.")
