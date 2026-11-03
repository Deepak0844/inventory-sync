"""The `sync_variants` job: copy the shop's Variants so mappings can name them by SKU."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.repos.catalog import CatalogRepo
from app.db.repos.jobs import JobRecord
from app.worker.deps import Deps
from app.worker.notify import notify_once
from app.worker.shop import connect


def handle_sync_variants(deps: Deps, session: Session, job: JobRecord) -> None:
    """Add or refresh every Shopify Variant that has a SKU.

    Shopify allows two Variants to share a SKU but mappings are by SKU, so the
    second one is skipped and the owner is told.
    """
    shopify = connect(deps, session, None, "Variants were not synced")
    if shopify is None:
        return
    catalog, skipped = CatalogRepo(session), []
    for variant in shopify.all_variants():
        try:
            catalog.upsert_variant(variant.id, variant.sku, variant.title)
        except IntegrityError:
            session.rollback()
            skipped.append(variant.sku)
    if skipped:
        notify_once(session, "shopify_error", None,
                    f"{len(skipped)} Variant(s) skipped because their SKU is used twice "
                    f"({', '.join(skipped[:5])}).", deps.now())
