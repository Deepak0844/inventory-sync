"""Getting a Shopify API for a job, and telling the owner when that is not possible."""

from sqlalchemy.orm import Session

from app.db.repos.settings import SettingsRepo
from app.shopify.client import ShopifyError
from app.worker.deps import Deps, ShopifyApi
from app.worker.notify import notify_once


def connect(
    deps: Deps, session: Session, supplier_id: int | None, skipped: str
) -> ShopifyApi | None:
    """Return the Shopify API, or None after raising a `shopify_error` notification.

    `skipped` finishes the sentence "..., so <skipped>." in that notification.
    A job that cannot reach Shopify then ends cleanly instead of failing and retrying.
    """
    settings = SettingsRepo(session, deps.box)
    try:
        api = deps.shopify(settings.get(), settings.get_secrets())
    except ShopifyError:
        api = None
    if api is None:
        notify_once(session, "shopify_error", supplier_id,
                    f"Shopify is not set up or refused the login, so {skipped}.", deps.now())
    return api
