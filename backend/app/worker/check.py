"""The `check_supplier` job: log in, read every Listing, decide, hold or write.

The decisions themselves are pure functions in `app.engine`; this module only
loads their inputs and stores their outputs. Not responsible for scheduling.
"""

from collections import Counter
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.db.repos.approvals import ApprovalRepo, HeldChange
from app.db.repos.history import HistoryRepo
from app.db.repos.jobs import JobRecord, JobRepo
from app.db.repos.runs import RunRepo
from app.db.repos.settings import SettingsRepo
from app.db.repos.states import StateRepo
from app.db.repos.suppliers import SessionCookiesRepo, SupplierRecord, SupplierRepo
from app.engine.listing import ReadingRules, StockStatus, apply_reading
from app.engine.login_policy import LoginAction
from app.engine.plan import MappedVariant, plan_supplier_run
from app.engine.safety import KillSwitchRules
from app.engine.variant import Action, Reason, VariantState
from app.flows.definition import FlowDefinition
from app.flows.page import BrowserSession
from app.flows.results import Credentials, ReadingResult
from app.flows.runner import run_extract
from app.flows.session_store import EncryptedSessionStore
from app.scheduler.tick import has_open_job
from app.shopify.apply import apply_changes
from app.worker import queries
from app.worker.deps import Deps
from app.worker.login import login_with_policy
from app.worker.notify import notify_once, replace_notification
from app.worker.shop import connect

_PROBLEMS = {"blocked": "blocked", "browser_error": "supplier_unreachable"}


def handle_check_supplier(deps: Deps, session: Session, job: JobRecord) -> None:
    """Check one Supplier. A paused or missing Supplier is skipped.

    Every expected problem (login trouble, a vanished element, Shopify errors) is
    handled here as a notification and an Unknown reading; only a bug raises.
    """
    suppliers = SupplierRepo(session, deps.box)
    supplier = None if job.supplier_id is None else suppliers.get(job.supplier_id)
    if supplier is None or supplier.paused:
        return
    runs = RunRepo(session)
    run_id = runs.start(supplier.id, "check", deps.now())
    state, summary = "failed", "unexpected error"
    try:
        state, summary = _check(deps, session, supplier)
    finally:
        runs.finish(run_id, state, summary, deps.now())


def _check(deps: Deps, session: Session, supplier: SupplierRecord) -> tuple[str, str]:
    suppliers = SupplierRepo(session, deps.box)
    flow_json = suppliers.get_flow(supplier.id)
    credentials = suppliers.get_credentials(supplier.id)
    if flow_json is None or credentials is None:
        notify_once(session, "flow_failure", supplier.id,
                    f"{supplier.name}: add a flow and credentials before checks can run.",
                    deps.now())
        return "failed", "no flow or credentials"
    flow = FlowDefinition.model_validate(flow_json)
    store = EncryptedSessionStore(deps.box, SessionCookiesRepo(session, supplier.id, deps.now))
    with deps.browser() as browser:
        if login_with_policy(deps, session, supplier, flow, credentials, browser,
                             store) is not LoginAction.DONE:
            return "stopped", "login did not complete"
        reads = _read_listings(deps, session, supplier, flow, credentials, browser, store)
    _decide_and_apply(deps, session, supplier, reads.known_ids)
    if reads.known or not reads.total:
        suppliers.update(supplier.id, last_success_at=deps.now())
    return "ok", f"{reads.total} listings, {reads.total - reads.known} unknown"


class _Reads:
    def __init__(self) -> None:
        self.total = 0
        self.known = 0
        self.known_ids: set[int] = set()


def _read_listings(
    deps: Deps, session: Session, supplier: SupplierRecord, flow: FlowDefinition,
    credentials: Credentials, browser: BrowserSession, store: EncryptedSessionStore,
) -> _Reads:
    page = browser.page
    rules = ReadingRules(supplier.out_confirm_reads, supplier.in_confirm_reads,
                         supplier.confirm_gap_min * 60.0, supplier.removed_as_unknown)
    states, history = StateRepo(session), HistoryRepo(session)
    reads, problems, relogged, pending_out = _Reads(), Counter[str](), False, False
    for listing_id, url in queries.supplier_listings(session, supplier.id):
        reading = run_extract(flow, page, url)
        if reading.error_kind == "session_lost" and not relogged:
            relogged = True
            store.clear()  # PLAN.md section 6: restart the login once
            if login_with_policy(deps, session, supplier, flow, credentials, browser,
                                 store) is not LoginAction.DONE:
                break
            reading = run_extract(flow, page, url)
        now = deps.clock.now()
        reads.total += 1
        history.add_reading(listing_id, reading.result.value, reading.error_kind,
                            reading.quantity, datetime.fromtimestamp(now, UTC))
        old = states.get_listing_state(listing_id)
        new = apply_reading(old, reading.result, now, rules, reading.quantity)
        states.save_listing_state(listing_id, new)
        if new.removed and not old.removed:
            notify_once(session, "listing_removed", supplier.id,
                        f"{supplier.name}: a Listing page was removed ({url}).", deps.now())
        pending_out = pending_out or new.streak_kind is StockStatus.OUT_OF_STOCK
        if reading.result is ReadingResult.UNKNOWN:
            problems[reading.error_kind or "unknown"] += 1
            if reading.error_kind == "blocked":
                SupplierRepo(session, deps.box).update(supplier.id, blocked=True)
                break
        else:
            reads.known += 1
            reads.known_ids.add(listing_id)
    _report(deps, session, supplier, problems)
    gap = timedelta(minutes=supplier.confirm_gap_min)
    if pending_out and not has_open_job(session, "check_supplier", supplier.id,
                                        later_than=deps.now()):
        JobRepo(session).enqueue("check_supplier", supplier.id, {"confirm": True},
                                 deps.now() + gap, deps.now())
    return reads


def _report(deps: Deps, session: Session, supplier: SupplierRecord,
            problems: Counter[str]) -> None:
    for error_kind, count in problems.items():
        kind = _PROBLEMS.get(error_kind, "flow_failure")
        notify_once(session, kind, supplier.id,
                    f"{supplier.name}: {count} Listing(s) could not be read ({error_kind}).",
                    deps.now())


def _decide_and_apply(
    deps: Deps, session: Session, supplier: SupplierRecord, read_ids: set[int]
) -> None:
    settings_repo = SettingsRepo(session, deps.box)
    settings = settings_repo.get()
    states, history = StateRepo(session), HistoryRepo(session)
    mapped = queries.mapped_variants(session, supplier.id)
    listing_states = {str(lid): states.get_listing_state(lid)
                      for row in mapped for lid in row.listing_ids}
    old = {row.gid: states.get_variant_state(row.variant_id) for row in mapped}
    plan = plan_supplier_run(
        listing_states,
        [MappedVariant(r.gid, [str(i) for i in r.listing_ids]) for r in mapped],
        {gid: None if rec is None else VariantState(rec.state) for gid, rec in old.items()},
        supplier.max_quantity,
        len(queries.supplier_listings(session, supplier.id)),
        KillSwitchRules(settings.kill_switch_percent, settings.kill_switch_max_flips),
    )
    by_gid = {r.gid: r for r in mapped}
    now = deps.now()
    if plan.held:
        held = []
        for c in plan.held:
            previous = old[c.variant_id]
            held.append(HeldChange(by_gid[c.variant_id].variant_id,
                                   None if previous is None else previous.state, "sold_out", 0))
        total = _hold(session, supplier.id, held, now)
        replace_notification(session, "pending_approval", supplier.id,
                             f"{supplier.name}: {total} Variants would sell out at once. "
                             "Review them before anything changes in Shopify.", now)
    # The per-check quantity refresh needs a fresh reading: after a failed check the
    # Variant keeps its last known state, and rewriting Shopify then would be a guess.
    applied = [c for c in plan.applied
               if c.decision.reason is not Reason.REFRESH
               or read_ids & set(by_gid[c.variant_id].listing_ids)]
    if not applied:
        return
    shopify = connect(deps, session, supplier.id, "no inventory was changed")
    if shopify is None:
        return
    report = apply_changes(applied, shopify)
    for change in report.applied:
        row, previous = by_gid[change.variant_id], old[change.variant_id]
        to_state = "sold_out" if change.decision.action is Action.SELL_OUT else "available"
        from_state = None if previous is None else previous.state
        if to_state != from_state:
            history.record_change(row.variant_id, from_state, to_state,
                                  change.decision.reason.value if change.decision.reason else "",
                                  "auto", now, supplier.id)
        states.save_variant_state(row.variant_id, to_state, now, change.decision.quantity)
    if report.failed:
        skus = ", ".join(by_gid[f.change.variant_id].sku for f in report.failed[:5])
        notify_once(session, "shopify_error", supplier.id,
                    f"{supplier.name}: Shopify did not accept {len(report.failed)} update(s) "
                    f"({skus}).", now)


def _hold(session: Session, supplier_id: int, held: list[HeldChange], now: datetime) -> int:
    """Hold changes for approval, joining the Supplier's open batch if it has one.

    Returns how many Variants the batch now holds.
    """
    approvals = ApprovalRepo(session)
    open_batch = next((a for a in approvals.list_pending() if a.supplier_id == supplier_id), None)
    if open_batch is None:
        approvals.create(supplier_id, held, now)
        return len(held)
    approvals.merge_changes(open_batch.id, held)
    return len({c.variant_id for c in open_batch.changes} | {c.variant_id for c in held})
