"""Flagged order routes."""

from fastapi import APIRouter

from app.api.deps import Db, protected
from app.api.schemas import FlaggedOrderOut, OrderVariantOut
from app.services import workflow

router = APIRouter(**protected(tags=["orders"]))


@router.get("/orders/flagged")
def flagged(session: Db) -> list[FlaggedOrderOut]:
    """List orders flagged "verify with Supplier". The system only flags; it never cancels."""
    return [
        FlaggedOrderOut(
            order_id=o.order_id, name=o.name, created_at=o.created_at, reasons=o.reasons,
            variants=[OrderVariantOut(sku=sku, reason=reason) for sku, reason in o.variants],
        )
        for o in workflow.flagged_orders(session)
    ]
