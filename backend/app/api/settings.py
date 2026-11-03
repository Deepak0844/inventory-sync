"""Settings routes. Secrets are write-only."""

from fastapi import APIRouter

from app.api.deps import Box, Db, Shopify, protected
from app.api.schemas import (
    KillSwitchSettings,
    MailboxOut,
    SettingsIn,
    SettingsOut,
    ShopifyOut,
    ShopifyTestOut,
)
from app.db.repos.settings import SettingsRecord
from app.services import settings as service

router = APIRouter(**protected(tags=["settings"]))


def _out(r: SettingsRecord) -> SettingsOut:
    return SettingsOut(
        shopify=ShopifyOut(shop_domain=r.shop_domain, client_id=r.client_id,
                           has_client_secret=r.has_client_secret),
        mailbox=MailboxOut(host=r.mailbox_host, user=r.mailbox_user,
                           has_password=r.has_mailbox_password),
        kill_switch=KillSwitchSettings(percent=r.kill_switch_percent,
                                       max_flips=r.kill_switch_max_flips),
        sold_out_window_h=r.sold_out_window_h, order_poll_min=r.order_poll_min,
    )


@router.get("/settings")
def get_settings(session: Db, box: Box) -> SettingsOut:
    """Return the settings; secrets appear only as has_* flags."""
    return _out(service.get_settings(session, box))


@router.put("/settings")
def put_settings(body: SettingsIn, session: Db, box: Box) -> SettingsOut:
    """Change any subset of the settings. A missing secret keeps the stored one."""
    fields: dict[str, object] = {}
    if body.shopify:
        fields |= body.shopify.model_dump(exclude_none=True)
    if body.mailbox:
        fields |= {f"mailbox_{k}": v for k, v in body.mailbox.model_dump(exclude_none=True).items()}
    if body.kill_switch:
        fields |= {"kill_switch_percent": body.kill_switch.percent,
                   "kill_switch_max_flips": body.kill_switch.max_flips}
    fields |= body.model_dump(
        include={"sold_out_window_h", "order_poll_min", "client_secret", "mailbox_password"},
        exclude_none=True,
    )
    return _out(service.update_settings(session, box, **fields))


@router.post("/settings/shopify/test")
def test_shopify(session: Db, box: Box, factory: Shopify) -> ShopifyTestOut:
    """Check the stored Shopify credentials without writing inventory."""
    ok, detail = service.check_shopify(session, box, factory)
    return ShopifyTestOut(ok=ok, detail=detail)
