"""The `apply_approval` job: write what the owner approved to Shopify."""

from sqlalchemy.orm import Session

from app.db.repos.history import HistoryRepo
from app.db.repos.jobs import JobRecord
from app.db.repos.notifications import NotificationRepo
from app.db.repos.states import StateRepo
from app.engine.changes import VariantChange
from app.engine.listing import StockStatus
from app.engine.variant import Action, Decision, Reason
from app.shopify.apply import apply_changes
from app.worker import queries
from app.worker.deps import Deps
from app.worker.notify import notify_once
from app.worker.shop import connect


class ApprovalNotApplied(Exception):
    """Approved changes could not all be written, so the job is retried later.

    The approval stays approved and each retry writes only what is still missing,
    so an approved batch is never silently lost.
    """


def handle_apply_approval(deps: Deps, session: Session, job: JobRecord) -> None:
    """Apply an approved batch. Does nothing unless the approval is in the approved state.

    Changes whose Variant is already in the approved state are skipped, so a retry
    writes only what failed. A Sold Out change is skipped (and the owner told) when a
    mapped Listing is In Stock again, because a batch can be approved long after it
    was held.

    Raises:
        ApprovalNotApplied: if Shopify is unavailable or rejected any change.
    """
    changes = queries.approved_changes(session, int(job.payload["approval_id"]))
    if not changes:
        return
    states, history = StateRepo(session), HistoryRepo(session)
    now = deps.now()
    todo, restocked = [], []
    for c in changes:
        current = states.get_variant_state(c.variant_id)
        if current is not None and current.state == c.to_state:
            continue  # applied by an earlier attempt
        if c.to_state == "sold_out" and any(
                states.get_listing_state(lid).status is StockStatus.IN_STOCK
                for lid in queries.variant_listing_ids(session, c.variant_id)):
            restocked.append(c.sku)
            continue
        todo.append(c)
    if restocked:
        NotificationRepo(session).add(
            "pending_approval", job.supplier_id,
            f"Approved sell-out skipped for {', '.join(restocked)}: a Listing is in stock again.",
            now)
    if not todo:
        return
    shopify = connect(deps, session, job.supplier_id, "the approved changes were not written")
    if shopify is None:
        raise ApprovalNotApplied("Shopify is not available")
    sell_out = Decision(Action.SELL_OUT, 0, Reason.ALL_OUT_OF_STOCK)
    by_gid = {c.gid: c for c in todo}
    report = apply_changes([
        VariantChange(c.gid, sell_out if c.to_state == "sold_out"
                      else Decision(Action.SET_AVAILABLE, c.quantity, Reason.RESTORE))
        for c in todo], shopify)
    for change in report.applied:
        row = by_gid[change.variant_id]
        before = states.get_variant_state(row.variant_id)
        if before is None or before.state != row.to_state:
            history.record_change(row.variant_id, None if before is None else before.state,
                                  row.to_state, "approved", "manual", now, job.supplier_id)
        states.save_variant_state(row.variant_id, row.to_state, now, row.quantity)
    if report.failed:
        notify_once(session, "shopify_error", job.supplier_id,
                    f"Shopify did not accept {len(report.failed)} approved update(s).", now)
        raise ApprovalNotApplied(f"{len(report.failed)} approved update(s) failed")
