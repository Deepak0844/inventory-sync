from datetime import timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.db.repos.catalog import CatalogRepo
from app.db.repos.history import HistoryRepo
from app.db.repos.states import StateRepo
from app.engine.listing import ListingState, StockStatus
from tests.api.conftest import T0, Clock


def add_supplier(auth: TestClient, name: str = "Supplier A", interval: int = 120) -> int:
    r = auth.post("/api/suppliers",
                  json={"name": name, "site_url": "https://a.example", "interval_min": interval})
    return int(r.json()["id"])


def add_variant(factory: sessionmaker[Session], sku: str) -> int:
    with factory() as session:
        return CatalogRepo(session).upsert_variant(f"gid://shopify/ProductVariant/{sku}", sku, sku)


def csv_file(body: str) -> dict[str, Any]:
    return {"files": {"file": ("listings.csv", body.encode(), "text/csv")}}


def import_csv(auth: TestClient, body: str) -> Any:
    return auth.post("/api/listings/import", **csv_file(body))


def test_import_creates_listings_and_maps_them(
    auth: TestClient, factory: sessionmaker[Session]
) -> None:
    add_supplier(auth)
    add_variant(factory, "SKU-1")
    r = import_csv(
        auth, "sku,supplier,url,selection_hint\nSKU-1,Supplier A,https://a.example/1,L\n"
    )
    assert r.status_code == 200 and r.json() == {"created": 1, "updated": 0, "errors": []}
    listings = auth.get("/api/listings").json()
    assert listings["total"] == 1 and listings["items"][0]["selection_hint"] == "L"
    assert listings["items"][0]["status"] == "unknown" and listings["next_cursor"] is None


def test_importing_the_same_file_again_updates_instead_of_duplicating(
    auth: TestClient, factory: sessionmaker[Session]
) -> None:
    add_supplier(auth)
    add_variant(factory, "SKU-1")
    body = "sku,supplier,url\nSKU-1,Supplier A,https://a.example/1\n"
    import_csv(auth, body)
    again = import_csv(auth, body).json()
    assert again["created"] == 0 and again["updated"] == 1
    assert auth.get("/api/listings").json()["total"] == 1


def test_good_rows_are_applied_when_others_fail(
    auth: TestClient, factory: sessionmaker[Session]
) -> None:
    add_supplier(auth)
    add_variant(factory, "SKU-1")
    body = ("sku,supplier,url\nSKU-1,Supplier A,https://a.example/1\n"
            "NOPE,Supplier A,https://a.example/2\nSKU-1,Ghost,https://a.example/3\n")
    result = import_csv(auth, body).json()
    assert result["created"] == 1
    assert [(e["row"], e["message"]) for e in result["errors"]] == [
        (3, "Unknown SKU NOPE"), (4, "Unknown Supplier Ghost")]


def test_a_file_without_the_required_columns_is_rejected(auth: TestClient) -> None:
    assert import_csv(auth, "foo,bar\n1,2\n").status_code == 422


def test_an_oversized_upload_is_rejected(auth: TestClient) -> None:
    big = "sku,supplier,url\n" + "S,Supplier A,https://a.example/1\n" * 40_000
    assert import_csv(auth, big).status_code == 413


def test_a_non_utf8_file_is_rejected(auth: TestClient) -> None:
    r = auth.post("/api/listings/import",
                  files={"file": ("x.csv", b"sku,supplier,url\n\xff\xfe\n", "text/csv")})
    assert r.status_code == 422


def test_listings_can_be_filtered_and_paged(
    auth: TestClient, factory: sessionmaker[Session]
) -> None:
    a, b = add_supplier(auth, "Supplier A"), add_supplier(auth, "Supplier B")
    add_variant(factory, "S1")
    import_csv(auth, "sku,supplier,url\n" + "".join(
        f"S1,{'Supplier A' if i % 2 else 'Supplier B'},https://x.example/{i}\n" for i in range(5)))
    assert auth.get("/api/listings", params={"supplier_id": a}).json()["total"] == 2
    assert auth.get("/api/listings", params={"supplier_id": b}).json()["total"] == 3
    page = auth.get("/api/listings", params={"limit": 2}).json()
    assert len(page["items"]) == 2 and page["total"] == 5 and page["next_cursor"]
    rest = auth.get("/api/listings", params={"limit": 10, "cursor": page["next_cursor"]}).json()
    assert len(rest["items"]) == 3 and rest["next_cursor"] is None
    assert auth.get("/api/listings", params={"q": "/3"}).json()["total"] == 1


def seed_variant(auth: TestClient, factory: sessionmaker[Session], sku: str = "SKU-1",
                 interval: int = 120) -> tuple[int, int]:
    add_supplier(auth, interval=interval)
    vid = add_variant(factory, sku)
    import_csv(auth, f"sku,supplier,url\n{sku},Supplier A,https://a.example/{sku}\n")
    return vid, int(auth.get("/api/listings").json()["items"][0]["id"])


def test_a_variant_lists_its_listings_and_reading_strip(
    auth: TestClient, factory: sessionmaker[Session]
) -> None:
    vid, lid = seed_variant(auth, factory)
    with factory() as session:
        for i, result in enumerate(["in_stock", "out_of_stock"]):
            HistoryRepo(session).add_reading(lid, result, None, None, T0 + timedelta(minutes=i))
    item = auth.get("/api/variants").json()["items"][0]
    assert item["sku"] == "SKU-1" and item["state"] is None
    supplier_id = item["listings"][0]["supplier_id"]
    assert item["listings"] == [{"listing_id": lid, "supplier_id": supplier_id, "priority": 1}]
    assert [r["result"] for r in item["readings"]] == ["in_stock", "out_of_stock"]


def mark_fresh(factory: sessionmaker[Session], lid: int, at: Any) -> None:
    with factory() as session:
        StateRepo(session).save_listing_state(
            lid, ListingState(status=StockStatus.IN_STOCK, last_success_at=at.timestamp()))


def test_a_variant_never_checked_is_stale(auth: TestClient, factory: sessionmaker[Session]) -> None:
    seed_variant(auth, factory)
    assert auth.get("/api/variants").json()["items"][0]["stale"] is True


def test_a_recently_checked_variant_is_not_stale_until_twice_the_interval(
    auth: TestClient, factory: sessionmaker[Session], clock: Clock
) -> None:
    _, lid = seed_variant(auth, factory, interval=60)
    mark_fresh(factory, lid, T0)
    clock.advance(minutes=119)
    assert auth.get("/api/variants").json()["items"][0]["stale"] is False
    clock.advance(minutes=2)
    assert auth.get("/api/variants").json()["items"][0]["stale"] is True


def test_the_stale_filter_keeps_totals_honest(
    auth: TestClient, factory: sessionmaker[Session]
) -> None:
    _, lid = seed_variant(auth, factory, "SKU-1")
    add_variant(factory, "SKU-2")
    mark_fresh(factory, lid, T0)
    stale = auth.get("/api/variants", params={"stale": "true"}).json()
    fresh = auth.get("/api/variants", params={"stale": "false"}).json()
    assert [i["sku"] for i in stale["items"]] == ["SKU-2"] and stale["total"] == 1
    assert [i["sku"] for i in fresh["items"]] == ["SKU-1"] and fresh["total"] == 1


def test_variants_can_be_filtered_by_state_and_search(
    auth: TestClient, factory: sessionmaker[Session]
) -> None:
    v1, _ = seed_variant(auth, factory, "SKU-1")
    add_variant(factory, "OTHER")
    with factory() as session:
        from app.db.repos.states import StateRepo as S
        S(session).save_variant_state(v1, "sold_out", T0, 0)
    sold_out = auth.get("/api/variants", params={"state": "sold_out"}).json()["items"]
    assert [i["sku"] for i in sold_out] == ["SKU-1"]
    assert auth.get("/api/variants", params={"q": "other"}).json()["total"] == 1


def test_mappings_can_be_read_and_replaced(
    auth: TestClient, factory: sessionmaker[Session]
) -> None:
    vid, lid = seed_variant(auth, factory)
    assert auth.get(f"/api/variants/{vid}/mappings").json() == [{"listing_id": lid, "priority": 1}]
    new = [{"listing_id": lid, "priority": 3}]
    assert auth.put(f"/api/variants/{vid}/mappings", json=new).status_code == 200
    assert auth.get(f"/api/variants/{vid}/mappings").json() == new


def test_replacing_with_an_unknown_listing_changes_nothing(
    auth: TestClient, factory: sessionmaker[Session]
) -> None:
    vid, lid = seed_variant(auth, factory)
    bad = auth.put(f"/api/variants/{vid}/mappings", json=[{"listing_id": 999, "priority": 1}])
    assert bad.status_code == 422
    assert auth.get(f"/api/variants/{vid}/mappings").json() == [{"listing_id": lid, "priority": 1}]


def test_duplicate_listings_in_a_mapping_are_rejected(
    auth: TestClient, factory: sessionmaker[Session]
) -> None:
    vid, lid = seed_variant(auth, factory)
    dup = [{"listing_id": lid, "priority": 1}, {"listing_id": lid, "priority": 2}]
    assert auth.put(f"/api/variants/{vid}/mappings", json=dup).status_code == 422


def test_mappings_of_an_unknown_variant_are_404(auth: TestClient) -> None:
    assert auth.get("/api/variants/999/mappings").status_code == 404
    assert auth.put("/api/variants/999/mappings", json=[]).status_code == 404


def test_catalog_routes_need_a_session(client: TestClient) -> None:
    for url in ("/api/listings", "/api/variants", "/api/variants/1/mappings"):
        assert client.get(url).status_code == 401
    assert client.post("/api/listings/import").status_code == 401


def test_sql_in_search_text_is_just_text(auth: TestClient) -> None:
    hostile = {"q": "'; DROP TABLE variants; --"}
    assert auth.get("/api/variants", params=hostile).json()["total"] == 0
