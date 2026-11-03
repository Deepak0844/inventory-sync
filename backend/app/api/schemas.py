"""Request and response bodies shared by the route modules (see docs/api.md)."""

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Out(BaseModel):
    """Base for response models built from service dataclasses."""

    model_config = ConfigDict(from_attributes=True)


class SupplierOut(Out):
    id: int
    name: str
    site_url: str
    stock_source: str
    interval_min: int
    out_confirm_reads: int
    in_confirm_reads: int
    confirm_gap_min: int
    removed_as_unknown: bool
    max_quantity: int
    two_fa_methods: list[str]
    code_window_min: int
    paused: bool
    pause_reason: str | None
    health: str
    last_success_at: datetime | None
    session_age_s: int | None
    listing_count: int


class SupplierSettings(BaseModel):
    """Fields a client may set on a Supplier. Health and secrets are not among them."""

    model_config = ConfigDict(extra="forbid")

    stock_source: Literal["scrape", "feed"] = "scrape"
    interval_min: int = Field(ge=1, le=1440)
    out_confirm_reads: int = Field(default=2, ge=1, le=10)
    in_confirm_reads: int = Field(default=1, ge=1, le=10)
    confirm_gap_min: int = Field(default=30, ge=1, le=1440)
    removed_as_unknown: bool = False
    max_quantity: int = Field(default=100, ge=1)
    two_fa_methods: list[Literal["ui_code", "email_code"]] = ["ui_code"]
    code_window_min: int = Field(default=10, ge=1, le=120)


class SupplierCreate(SupplierSettings):
    name: str = Field(min_length=1, max_length=200)
    site_url: str = Field(min_length=1)


class SupplierPatch(BaseModel):
    """Any subset of the editable fields."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    site_url: str | None = Field(default=None, min_length=1)
    stock_source: Literal["scrape", "feed"] | None = None
    interval_min: int | None = Field(default=None, ge=1, le=1440)
    out_confirm_reads: int | None = Field(default=None, ge=1, le=10)
    in_confirm_reads: int | None = Field(default=None, ge=1, le=10)
    confirm_gap_min: int | None = Field(default=None, ge=1, le=1440)
    removed_as_unknown: bool | None = None
    max_quantity: int | None = Field(default=None, ge=1)
    two_fa_methods: list[Literal["ui_code", "email_code"]] | None = None
    code_window_min: int | None = Field(default=None, ge=1, le=120)


class CredentialsIn(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class CredentialsOut(BaseModel):
    username: str | None
    has_password: bool


class RunOut(Out):
    id: int
    kind: str
    state: str
    started_at: datetime
    finished_at: datetime | None
    summary: str


class RunsOut(BaseModel):
    items: list[RunOut]


FlowJson = dict[str, Any]


class ListingOut(Out):
    id: int
    supplier_id: int
    url: str
    selection_hint: str
    status: str
    quantity: int | None
    removed: bool
    last_success_at: datetime | None


class ListingsOut(Out):
    items: list[ListingOut]
    total: int
    next_cursor: str | None


class ImportErrorOut(BaseModel):
    row: int
    message: str


class ImportOut(BaseModel):
    created: int
    updated: int
    errors: list[ImportErrorOut]


class MappingOut(Out):
    listing_id: int
    priority: int


class MappingIn(BaseModel):
    listing_id: int
    priority: int = Field(ge=1)


class VariantListingOut(Out):
    listing_id: int
    supplier_id: int
    priority: int


class ReadingOut(Out):
    result: str
    read_at: datetime


class VariantOut(BaseModel):
    id: int
    shopify_variant_id: str
    sku: str
    title: str
    state: str | None
    sold_out_at: datetime | None
    stale: bool
    listings: list[VariantListingOut]
    readings: list[ReadingOut]


class VariantsOut(BaseModel):
    items: list[VariantOut]
    total: int
    next_cursor: str | None


class ApprovalChangeOut(Out):
    variant_id: int
    sku: str
    from_state: str | None
    to_state: str


class ApprovalOut(Out):
    id: int
    supplier_id: int
    supplier_name: str
    created_at: datetime
    changes: list[ApprovalChangeOut]


class NotificationOut(BaseModel):
    id: int
    kind: str
    supplier_id: int | None
    supplier_name: str | None
    message: str
    created_at: datetime
    resolved_at: datetime | None
    screenshot_url: str | None


class OrderVariantOut(BaseModel):
    sku: str
    reason: str


class FlaggedOrderOut(BaseModel):
    order_id: str
    name: str
    created_at: datetime
    reasons: list[str]
    variants: list[OrderVariantOut]


class KpisOut(BaseModel):
    sold_out: int
    in_stock: int
    stale: int
    pending: int


class DayCountOut(BaseModel):
    date: date
    count: int


class SupplierHealthOut(Out):
    id: int
    name: str
    health: str
    last_success_at: datetime | None


class RecentChangeOut(BaseModel):
    at: datetime
    sku: str
    from_state: str | None
    to_state: str
    reason: str


class OverviewOut(BaseModel):
    updated_at: datetime
    kpis: KpisOut
    sold_out_by_day: list[DayCountOut]
    suppliers: list[SupplierHealthOut]
    recent_changes: list[RecentChangeOut]


class RedStripOut(BaseModel):
    supplier_id: int
    supplier_name: str
    last_success_at: datetime


class BannerCountsOut(BaseModel):
    approvals: int
    orders: int
    notifications: int


class BannerOut(BaseModel):
    red_strip: list[RedStripOut]
    counts: BannerCountsOut


class ShopifyOut(BaseModel):
    shop_domain: str
    client_id: str
    has_client_secret: bool


class MailboxOut(BaseModel):
    host: str
    user: str
    has_password: bool


class KillSwitchSettings(BaseModel):
    percent: float = Field(gt=0, le=1)
    max_flips: int = Field(ge=1)


class SettingsOut(BaseModel):
    shopify: ShopifyOut
    mailbox: MailboxOut
    kill_switch: KillSwitchSettings
    sold_out_window_h: int
    order_poll_min: int


class ShopifyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shop_domain: str | None = None
    client_id: str | None = None


class MailboxIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str | None = None
    user: str | None = None


class SettingsIn(BaseModel):
    """Any subset of the settings. Secrets are accepted here and never returned."""

    model_config = ConfigDict(extra="forbid")

    shopify: ShopifyIn | None = None
    mailbox: MailboxIn | None = None
    kill_switch: KillSwitchSettings | None = None
    sold_out_window_h: int | None = Field(default=None, ge=1)
    order_poll_min: int | None = Field(default=None, ge=1)
    client_secret: str | None = None
    mailbox_password: str | None = None


class ShopifyTestOut(BaseModel):
    ok: bool
    detail: str
