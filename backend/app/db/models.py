"""SQLAlchemy table definitions (PLAN.md section 13 plus the dashboard's needs).

Not responsible for queries or business rules; repositories in `app.db.repos`
read and write these and hand out plain dataclasses, never these objects.
Secrets are stored encrypted in columns ending in `_enc`.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

Timestamp = DateTime(timezone=True)


class Base(DeclarativeBase):
    """Declarative base for every table."""


class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    totp_secret_enc: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(Timestamp)


class AdminSession(Base):
    __tablename__ = "admin_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("admin_users.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(128), unique=True)
    created_at: Mapped[datetime] = mapped_column(Timestamp)
    expires_at: Mapped[datetime] = mapped_column(Timestamp)


class LoginThrottle(Base):
    """One row per failed sign-in, used to rate limit by username."""

    __tablename__ = "login_throttle"
    __table_args__ = (Index("ix_login_throttle_username_at", "username", "attempted_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(100))
    attempted_at: Mapped[datetime] = mapped_column(Timestamp)


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    site_url: Mapped[str] = mapped_column(Text)
    stock_source: Mapped[str] = mapped_column(String(20), default="scrape")
    interval_min: Mapped[int] = mapped_column(Integer, default=180)
    out_confirm_reads: Mapped[int] = mapped_column(Integer, default=2)
    in_confirm_reads: Mapped[int] = mapped_column(Integer, default=1)
    confirm_gap_min: Mapped[int] = mapped_column(Integer, default=30)
    removed_as_unknown: Mapped[bool] = mapped_column(Boolean, default=False)
    max_quantity: Mapped[int] = mapped_column(Integer, default=100)
    two_fa_methods: Mapped[list[str]] = mapped_column(JSON, default=list)
    code_window_min: Mapped[int] = mapped_column(Integer, default=10)
    username_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    password_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    flow_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    flow_draft_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    session_cookies_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    session_saved_at: Mapped[datetime | None] = mapped_column(Timestamp, nullable=True)
    paused: Mapped[bool] = mapped_column(Boolean, default=False)
    pause_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_success_at: Mapped[datetime | None] = mapped_column(Timestamp, nullable=True)
    waiting_for_code_until: Mapped[datetime | None] = mapped_column(Timestamp, nullable=True)
    created_at: Mapped[datetime] = mapped_column(Timestamp)


class Listing(Base):
    __tablename__ = "listings"
    __table_args__ = (UniqueConstraint("supplier_id", "url", "selection_hint"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id", ondelete="CASCADE"))
    url: Mapped[str] = mapped_column(Text)
    # Empty string, not NULL, so the unique constraint treats "no hint" as one value.
    selection_hint: Mapped[str] = mapped_column(Text, default="")


class Variant(Base):
    __tablename__ = "variants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shopify_variant_id: Mapped[str] = mapped_column(String(200), unique=True)
    sku: Mapped[str] = mapped_column(String(200), unique=True)
    title: Mapped[str] = mapped_column(Text, default="")


class Mapping(Base):
    __tablename__ = "mappings"
    __table_args__ = (UniqueConstraint("variant_id", "listing_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    variant_id: Mapped[int] = mapped_column(ForeignKey("variants.id", ondelete="CASCADE"))
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id", ondelete="CASCADE"))
    priority: Mapped[int] = mapped_column(Integer, default=1)


class ListingStateRow(Base):
    __tablename__ = "listing_states"

    listing_id: Mapped[int] = mapped_column(
        ForeignKey("listings.id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[str] = mapped_column(String(20), default="unknown")
    removed: Mapped[bool] = mapped_column(Boolean, default=False)
    quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(Timestamp, nullable=True)
    streak_kind: Mapped[str | None] = mapped_column(String(20), nullable=True)
    streak_count: Mapped[int] = mapped_column(Integer, default=0)
    streak_last_at: Mapped[float] = mapped_column(Float, default=0.0)


class VariantStateRow(Base):
    """What the system last set in Shopify. No row means the Variant is not managed yet."""

    __tablename__ = "variant_states"

    variant_id: Mapped[int] = mapped_column(
        ForeignKey("variants.id", ondelete="CASCADE"), primary_key=True
    )
    state: Mapped[str] = mapped_column(String(20))
    sold_out_at: Mapped[datetime | None] = mapped_column(Timestamp, nullable=True)
    last_written_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(Timestamp)


class Reading(Base):
    __tablename__ = "readings"
    __table_args__ = (Index("ix_readings_listing_read_at", "listing_id", "read_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id", ondelete="CASCADE"))
    result: Mapped[str] = mapped_column(String(30))
    error_kind: Mapped[str | None] = mapped_column(String(50), nullable=True)
    quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    read_at: Mapped[datetime] = mapped_column(Timestamp)
    screenshot_path: Mapped[str | None] = mapped_column(Text, nullable=True)


class InventoryChange(Base):
    __tablename__ = "inventory_changes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    variant_id: Mapped[int] = mapped_column(ForeignKey("variants.id", ondelete="CASCADE"))
    supplier_id: Mapped[int | None] = mapped_column(
        ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True
    )
    from_state: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_state: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(String(50))
    approval: Mapped[str] = mapped_column(String(20), default="auto")
    at: Mapped[datetime] = mapped_column(Timestamp)


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(30))
    state: Mapped[str] = mapped_column(String(30))
    started_at: Mapped[datetime] = mapped_column(Timestamp)
    finished_at: Mapped[datetime | None] = mapped_column(Timestamp, nullable=True)
    summary: Mapped[str] = mapped_column(Text, default="")


class FlowTestRun(Base):
    """One Test run from the flow builder. It never touches stock; see docs/api.md."""

    __tablename__ = "test_runs"
    __table_args__ = (Index("ix_test_runs_supplier_state", "supplier_id", "state"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id", ondelete="CASCADE"))
    state: Mapped[str] = mapped_column(String(30), default="queued")
    mode: Mapped[str] = mapped_column(String(20))
    request: Mapped[dict[str, Any]] = mapped_column(JSON)
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    reading: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    login_result: Mapped[str | None] = mapped_column(String(40), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(Timestamp)
    finished_at: Mapped[datetime | None] = mapped_column(Timestamp, nullable=True)


class Job(Base):
    """The Postgres job queue (ADR 0001), claimed with FOR UPDATE SKIP LOCKED."""

    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_state_run_after", "state", "run_after"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(30))
    supplier_id: Mapped[int | None] = mapped_column(
        ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=True
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    run_after: Mapped[datetime] = mapped_column(Timestamp)
    state: Mapped[str] = mapped_column(String(20), default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_at: Mapped[datetime | None] = mapped_column(Timestamp, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(Timestamp)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(40))
    supplier_id: Mapped[int | None] = mapped_column(
        ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=True
    )
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(Timestamp)
    resolved_at: Mapped[datetime | None] = mapped_column(Timestamp, nullable=True)
    screenshot_path: Mapped[str | None] = mapped_column(Text, nullable=True)


class Approval(Base):
    """A batch of changes held back by the kill switch (Pending Approval)."""

    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id", ondelete="CASCADE"))
    state: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(Timestamp)
    decided_at: Mapped[datetime | None] = mapped_column(Timestamp, nullable=True)


class ApprovalChange(Base):
    __tablename__ = "approval_changes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    approval_id: Mapped[int] = mapped_column(ForeignKey("approvals.id", ondelete="CASCADE"))
    variant_id: Mapped[int] = mapped_column(ForeignKey("variants.id", ondelete="CASCADE"))
    from_state: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_state: Mapped[str] = mapped_column(String(20))
    quantity: Mapped[int] = mapped_column(Integer, default=0)


class FlaggedOrder(Base):
    __tablename__ = "flagged_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[str] = mapped_column(String(100), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(Timestamp)
    flagged_at: Mapped[datetime] = mapped_column(Timestamp)
    lines_truncated: Mapped[bool] = mapped_column(Boolean, default=False)


class FlaggedOrderLine(Base):
    __tablename__ = "flagged_order_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    flagged_order_id: Mapped[int] = mapped_column(
        ForeignKey("flagged_orders.id", ondelete="CASCADE")
    )
    sku: Mapped[str] = mapped_column(String(200))
    reason: Mapped[str] = mapped_column(String(30))


class AppSettings(Base):
    """A single row (id = 1) of system-wide settings."""

    __tablename__ = "app_settings"
    __table_args__ = (CheckConstraint("id = 1", name="single_row"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    shop_domain: Mapped[str] = mapped_column(String(200), default="")
    client_id: Mapped[str] = mapped_column(String(200), default="")
    client_secret_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    mailbox_host: Mapped[str] = mapped_column(String(200), default="")
    mailbox_user: Mapped[str] = mapped_column(String(200), default="")
    mailbox_password_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    kill_switch_percent: Mapped[float] = mapped_column(Float, default=0.30)
    kill_switch_max_flips: Mapped[int] = mapped_column(Integer, default=20)
    sold_out_window_h: Mapped[int] = mapped_column(Integer, default=6)
    order_poll_min: Mapped[int] = mapped_column(Integer, default=10)


class PastedCode(Base):
    """A Login Code pasted in the dashboard, encrypted and consumed once."""

    __tablename__ = "pasted_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id", ondelete="CASCADE"))
    code_enc: Mapped[str] = mapped_column(Text)
    submitted_at: Mapped[datetime] = mapped_column(Timestamp)
