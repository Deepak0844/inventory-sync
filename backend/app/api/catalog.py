"""Listing, import, Variant and mapping routes."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, UploadFile

from app.api.deps import Box, Db, Now, protected
from app.api.schemas import (
    ImportErrorOut,
    ImportOut,
    ListingsOut,
    MappingIn,
    MappingOut,
    ReadingOut,
    VariantListingOut,
    VariantOut,
    VariantsOut,
)
from app.services import catalog as service

router = APIRouter(**protected(tags=["catalog"]))
Limit = Annotated[int, Query(ge=1, le=200)]


@router.get("/listings")
def listings(
    session: Db, supplier_id: int | None = None, q: str | None = None,
    status: str | None = None, cursor: str | None = None, limit: Limit = 50,
) -> ListingsOut:
    """Page through Listings, optionally by Supplier, search text or Stock Status."""
    return ListingsOut.model_validate(
        service.list_listings(session, supplier_id, q, status, cursor, limit)
    )


@router.post("/listings/import")
async def import_listings(file: UploadFile, session: Db, box: Box) -> ImportOut:
    """Import a CSV of `sku,supplier,url[,selection_hint]`.

    Valid rows are applied and each bad row is reported. 413 above 1 MB, 422 when the
    file itself is unusable.
    """
    data = await file.read(service.MAX_IMPORT_BYTES + 1)
    if len(data) > service.MAX_IMPORT_BYTES:
        raise HTTPException(status_code=413, detail="The file is larger than 1 MB")
    try:
        outcome = service.import_listings(session, box, data)
    except service.ImportRejected as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return ImportOut(
        created=outcome.created, updated=outcome.updated,
        errors=[ImportErrorOut(row=e.row, message=e.message) for e in outcome.errors],
    )


@router.get("/variants")
def variants(
    session: Db, box: Box, now: Now, state: str | None = None, stale: bool | None = None,
    q: str | None = None, cursor: str | None = None, limit: Limit = 50,
) -> VariantsOut:
    """Page through Variants with mappings, the last 12 readings and whether each is Stale."""
    page = service.list_variants(session, box, now, state, stale, q, cursor, limit)
    return VariantsOut(
        total=page.total, next_cursor=page.next_cursor,
        items=[
            VariantOut(
                id=v.row.id, shopify_variant_id=v.row.shopify_variant_id, sku=v.row.sku,
                title=v.row.title, state=v.row.state, sold_out_at=v.row.sold_out_at,
                stale=v.stale,
                listings=[VariantListingOut.model_validate(m) for m in v.row.listings],
                readings=[ReadingOut.model_validate(r) for r in v.row.readings],
            )
            for v in page.items
        ],
    )


@router.get("/variants/{variant_id}/mappings")
def get_mappings(variant_id: int, session: Db) -> list[MappingOut]:
    """Return the Variant's mapped Listings, highest priority first (404 if unknown)."""
    try:
        return [MappingOut.model_validate(m) for m in service.get_mappings(session, variant_id)]
    except service.UnknownVariant:
        raise HTTPException(status_code=404, detail="Variant not found") from None


@router.put("/variants/{variant_id}/mappings")
def put_mappings(variant_id: int, body: list[MappingIn], session: Db) -> list[MappingOut]:
    """Replace the Variant's mappings. 422 (and no change) for an unknown or repeated Listing."""
    try:
        saved = service.replace_mappings(
            session, variant_id, [(m.listing_id, m.priority) for m in body]
        )
    except service.UnknownVariant:
        raise HTTPException(status_code=404, detail="Variant not found") from None
    except service.InvalidMapping as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return [MappingOut.model_validate(m) for m in saved]
