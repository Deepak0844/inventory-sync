"""The `poll_orders` job: flag new orders that contain a risky Variant.

The system only flags. It never cancels an order or contacts a customer.
"""

from datetime import datetime

from sqlalchemy.orm import Session

from app.db.repos.jobs import JobRecord
from app.db.repos.orders import FlaggedLine, OrderRepo
from app.db.repos.settings import SettingsRepo
from app.db.repos.states import StateRepo
from app.engine.safety import VariantSafety, flag_order, is_variant_stale
from app.worker import queries
from app.worker.deps import Deps
from app.worker.shop import connect


def handle_poll_orders(deps: Deps, session: Session, job: JobRecord) -> None:
    """Read orders created since `payload["since"]` and flag the risky ones.

    Polls overlap on purpose and Shopify's filter is inclusive, so an order can
    arrive again; flagging is idempotent by order id. An order that was clear
    when first seen may be flagged on a later overlapping poll if one of its
    Variants has gone Stale in between (shortcut: harmless extra flag).
    """
    shopify = connect(deps, session, None, "orders were not checked")
    if shopify is None:
        return
    settings = SettingsRepo(session, deps.box).get()
    now = deps.now()
    states, orders = StateRepo(session), OrderRepo(session)
    window_s = settings.sold_out_window_h * 3600.0
    for order in shopify.recent_orders(str(job.payload["since"])):
        lines: list[FlaggedLine] = []
        for gid in order.variant_ids:
            info = queries.variant_info(session, gid)
            if info is None:
                continue  # not a Variant we manage
            sold_out_at = states.get_variant_state(info.variant_id)
            safety = VariantSafety(
                gid,
                is_variant_stale([states.get_listing_state(i) for i in info.listing_ids],
                                 deps.clock.now(), info.interval_min * 60.0),
                None if sold_out_at is None or sold_out_at.sold_out_at is None
                else sold_out_at.sold_out_at.timestamp())
            flag = flag_order([safety], deps.clock.now(), window_s)
            lines += [FlaggedLine(info.sku, reason.value) for reason in flag.reasons]
        if lines or order.lines_truncated:
            orders.flag(order.id, order.name,
                        datetime.fromisoformat(order.created_at.replace("Z", "+00:00")),
                        lines, order.lines_truncated, now)
