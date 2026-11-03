"""System settings and the Shopify connection check.

Not responsible for HTTP. Secrets are written but never read back out through here.
"""

from collections.abc import Callable
from typing import Any, Protocol

from sqlalchemy.orm import Session

from app.core.encryption import SecretBox
from app.core.masking import mask_secrets
from app.db.repos.settings import SettingsRecord, SettingsRepo

NOT_CONFIGURED = "Add the shop domain, client ID and client secret first"


class ShopifyCheck(Protocol):
    """What the "test connection" button needs from a Shopify client."""

    def check(self) -> str:
        """Verify the credentials without writing inventory. Returns a short description."""
        ...


ShopifyFactory = Callable[[str, str, str], ShopifyCheck]


def default_shopify_factory(shop: str, client_id: str, client_secret: str) -> ShopifyCheck:
    """Build the real client. The token exchange is wired up with the worker's Shopify job."""
    raise NotImplementedError("the Shopify connection check is not wired up yet")


def get_settings(session: Session, box: SecretBox) -> SettingsRecord:
    """Return the settings (secrets as has_* flags only)."""
    return SettingsRepo(session, box).get()


def update_settings(session: Session, box: SecretBox, **fields: Any) -> SettingsRecord:
    """Change only the given fields; a missing or None secret keeps the stored one."""
    repo = SettingsRepo(session, box)
    repo.update(**fields)
    return repo.get()


def check_shopify(session: Session, box: SecretBox, factory: ShopifyFactory) -> tuple[bool, str]:
    """Try the stored Shopify credentials without writing inventory.

    Returns:
        `(ok, detail)`. A failure is reported, not raised, and the client secret is masked
        out of the detail.
    """
    repo = SettingsRepo(session, box)
    config, secret = repo.get(), repo.get_secrets().client_secret
    if not (config.shop_domain and config.client_id and secret):
        return False, NOT_CONFIGURED
    try:
        return True, factory(config.shop_domain, config.client_id, secret).check()
    except Exception as exc:  # any client failure is a result for the owner, not a crash
        return False, mask_secrets(f"{type(exc).__name__}: {exc}", [secret])
