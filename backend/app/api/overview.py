"""Overview and shell banner routes."""

from fastapi import APIRouter

from app.api.deps import Box, Db, Now, protected
from app.api.schemas import (
    BannerCountsOut,
    BannerOut,
    DayCountOut,
    KpisOut,
    OverviewOut,
    RecentChangeOut,
    RedStripOut,
    SupplierHealthOut,
)
from app.services import overview as service

router = APIRouter(**protected(tags=["overview"]))


@router.get("/overview")
def overview(session: Db, box: Box, now: Now) -> OverviewOut:
    """The numbers behind "Is my stock trustworthy right now?"."""
    o = service.build_overview(session, box, now)
    return OverviewOut(
        updated_at=o.updated_at,
        kpis=KpisOut(sold_out=o.sold_out, in_stock=o.in_stock, stale=o.stale, pending=o.pending),
        sold_out_by_day=[DayCountOut(date=d.date, count=d.count) for d in o.sold_out_by_day],
        suppliers=[SupplierHealthOut.model_validate(s) for s in o.suppliers],
        recent_changes=[
            RecentChangeOut(at=c.at, sku=c.sku, from_state=c.from_state, to_state=c.to_state,
                            reason=c.reason)
            for c in o.recent_changes
        ],
    )


@router.get("/banner")
def banner(session: Db, box: Box, now: Now) -> BannerOut:
    """What the shell shows everywhere: overdue Suppliers and the queue counts."""
    b = service.build_banner(session, box, now)
    return BannerOut(
        red_strip=[RedStripOut(supplier_id=r.supplier_id, supplier_name=r.supplier_name,
                               last_success_at=r.last_success_at) for r in b.red_strip],
        counts=BannerCountsOut(approvals=b.approvals, orders=b.orders,
                               notifications=b.notifications),
    )
