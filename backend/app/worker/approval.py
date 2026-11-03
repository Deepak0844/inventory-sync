"""The `apply_approval` job: write what the owner approved to Shopify."""

from sqlalchemy.orm import Session

from app.db.repos.history import HistoryRepo
from app.db.repos.jobs import JobRecord
from app.db.repos.states import StateRepo
from app.engine.changes import VariantChange
from app.engine.variant import Action, Decision, Reason
from app.shopify.apply import apply_changes
from app.worker import queries
from app.worker.deps import Deps
from app.worker.notify import notify_once
from app.worker.shop import connect


def handle_apply_approval(deps: Deps, session: Session, job: JobRecord) -> None:
    """Apply an approved batch. Does nothing unless the approval is in the approved state.

    Safe to run twice: it writes the same quantities again and records a change
    only when the Variant's state actually moves.
    """
    changes = queries.approved_changes(session, int(job.payload["approval_id"]))
    if not changes:
        return
    shopify = connect(deps, session, job.supplier_id, "the approved changes were not written")
    if shopify is None:
        return
    now = deps.now()
    sell_out = Decision(Action.SELL_OUT, 0, Reason.ALL_OUT_OF_STOCK)
    by_gid = {c.gid: c for c in changes}
    report = apply_changes([
        VariantChange(c.gid, sell_out if c.to_state == "sold_out"
                      else Decision(Action.SET_AVAILABLE, c.quantity, Reason.RESTORE))
        for c in changes], shopify)
    states, history = StateRepo(session), HistoryRepo(session)
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
