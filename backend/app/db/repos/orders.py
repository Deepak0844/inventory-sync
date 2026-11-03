"""Orders flagged "verify with Supplier". Not responsible for deciding the flag."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import FlaggedOrder, FlaggedOrderLine


@dataclass(frozen=True)
class FlaggedLine:
    sku: str
    reason: str


@dataclass(frozen=True)
class FlaggedOrderRecord:
    order_id: str
    name: str
    created_at: datetime
    flagged_at: datetime
    lines_truncated: bool
    lines: list[FlaggedLine]


class OrderRepo:
    """Rows of `flagged_orders` and their lines."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def flag(
        self, order_id: str, name: str, created_at: datetime, lines: list[FlaggedLine],
        lines_truncated: bool, now: datetime,
    ) -> bool:
        """Flag an order. Returns False if it was already flagged (polls overlap)."""
        row_id = self._s.execute(
            insert(FlaggedOrder).values(order_id=order_id, name=name, created_at=created_at,
                                        flagged_at=now, lines_truncated=lines_truncated)
            .on_conflict_do_nothing(index_elements=["order_id"]).returning(FlaggedOrder.id)
        ).scalar_one_or_none()
        if row_id is not None:
            self._s.add_all(FlaggedOrderLine(flagged_order_id=row_id, sku=x.sku, reason=x.reason)
                            for x in lines)
        self._s.commit()
        return row_id is not None

    def list_flagged(self) -> list[FlaggedOrderRecord]:
        """Return flagged orders, newest first."""
        orders = self._s.scalars(select(FlaggedOrder).order_by(FlaggedOrder.created_at.desc(),
                                                               FlaggedOrder.id.desc()))
        result = []
        for o in orders:
            lines = self._s.scalars(select(FlaggedOrderLine)
                                    .where(FlaggedOrderLine.flagged_order_id == o.id)
                                    .order_by(FlaggedOrderLine.id))
            result.append(FlaggedOrderRecord(o.order_id, o.name, o.created_at, o.flagged_at,
                                             o.lines_truncated,
                                             [FlaggedLine(x.sku, x.reason) for x in lines]))
        return result
