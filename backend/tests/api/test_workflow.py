from datetime import timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.db.repos.approvals import ApprovalRepo, HeldChange
from app.db.repos.catalog import CatalogRepo
from app.db.repos.notifications import NotificationRepo
from app.db.repos.orders import FlaggedLine, OrderRepo
from tests.api.conftest import T0


def supplier(auth: TestClient, name: str = "Supplier A") -> int:
    r = auth.post("/api/suppliers",
                  json={"name": name, "site_url": "https://a.example", "interval_min": 120})
    return int(r.json()["id"])


def hold(factory: sessionmaker[Session], supplier_id: int, skus: list[str]) -> int:
    with factory() as session:
        ids = [CatalogRepo(session).upsert_variant(f"gid://{s}", s, s) for s in skus]
        return ApprovalRepo(session).create(
            supplier_id, [HeldChange(i, "available", "sold_out", 0) for i in ids], T0)


def queued(factory: sessionmaker[Session]) -> list[tuple[str, int | None, dict[str, int]]]:
    with factory() as session:
        rows = session.execute(
            text("SELECT kind, supplier_id, payload FROM jobs ORDER BY id")
        ).all()
    return [(r[0], r[1], r[2]) for r in rows]


def test_pending_approvals_list_their_changes(
    auth: TestClient, factory: sessionmaker[Session]
) -> None:
    sid = supplier(auth)
    aid = hold(factory, sid, ["SKU-1", "SKU-2"])
    [item] = auth.get("/api/approvals").json()
    assert (item["id"], item["supplier_id"], item["supplier_name"]) == (aid, sid, "Supplier A")
    assert [(c["sku"], c["from_state"], c["to_state"]) for c in item["changes"]] == [
        ("SKU-1", "available", "sold_out"), ("SKU-2", "available", "sold_out")]


def test_approving_queues_the_apply_job_once(
    auth: TestClient, factory: sessionmaker[Session]
) -> None:
    sid = supplier(auth)
    aid = hold(factory, sid, ["SKU-1"])
    assert auth.post(f"/api/approvals/{aid}/approve").status_code == 202
    assert auth.post(f"/api/approvals/{aid}/approve").status_code == 404
    assert queued(factory) == [("apply_approval", sid, {"approval_id": aid})]
    assert auth.get("/api/approvals").json() == []


def test_rejecting_discards_without_queueing(
    auth: TestClient, factory: sessionmaker[Session]
) -> None:
    aid = hold(factory, supplier(auth), ["SKU-1"])
    assert auth.post(f"/api/approvals/{aid}/reject").status_code == 204
    assert queued(factory) == [] and auth.get("/api/approvals").json() == []
    assert auth.post(f"/api/approvals/{aid}/approve").status_code == 404


def test_deciding_an_unknown_approval_is_404(auth: TestClient) -> None:
    assert auth.post("/api/approvals/999/approve").status_code == 404
    assert auth.post("/api/approvals/999/reject").status_code == 404


def raise_notification(
    factory: sessionmaker[Session], sid: int | None, kind: str = "flow_failure",
    shot: str | None = None,
) -> int:
    with factory() as session:
        return NotificationRepo(session).add(kind, sid, "Element not found", T0, shot)


def test_unresolved_notifications_are_the_default(
    auth: TestClient, factory: sessionmaker[Session]
) -> None:
    sid = supplier(auth)
    nid = raise_notification(factory, sid)
    [n] = auth.get("/api/notifications").json()
    assert (n["id"], n["kind"], n["supplier_name"], n["resolved_at"]) == (
        nid, "flow_failure", "Supplier A", None)
    assert n["screenshot_url"] is None
    assert auth.get("/api/notifications", params={"resolved": "true"}).json() == []


def test_resolving_moves_a_notification_to_the_resolved_list(
    auth: TestClient, factory: sessionmaker[Session]
) -> None:
    nid = raise_notification(factory, None, "daily_summary")
    assert auth.post(f"/api/notifications/{nid}/resolve").status_code == 204
    assert auth.get("/api/notifications").json() == []
    [done] = auth.get("/api/notifications", params={"resolved": "true"}).json()
    assert done["supplier_id"] is None and done["resolved_at"] is not None


def test_a_screenshot_is_served_from_the_screenshot_folder(
    auth: TestClient, factory: sessionmaker[Session], screenshots: Path
) -> None:
    (screenshots / "fail.png").write_bytes(b"\x89PNG-bytes")
    nid = raise_notification(factory, supplier(auth), shot=str(screenshots / "fail.png"))
    [n] = auth.get("/api/notifications").json()
    assert n["screenshot_url"] == f"/api/notifications/{nid}/screenshot"
    shot = auth.get(n["screenshot_url"])
    assert shot.status_code == 200 and shot.content == b"\x89PNG-bytes"


def test_a_screenshot_path_outside_the_folder_is_never_served(
    auth: TestClient, factory: sessionmaker[Session], screenshots: Path, tmp_path: Path
) -> None:
    secret = tmp_path / "secrets.txt"
    secret.write_text("do not leak")
    nid = raise_notification(factory, None, shot=str(secret))
    assert auth.get(f"/api/notifications/{nid}/screenshot").status_code == 404
    traversal = raise_notification(factory, None, shot=str(screenshots / ".." / "secrets.txt"))
    assert auth.get(f"/api/notifications/{traversal}/screenshot").status_code == 404


def test_a_notification_without_a_screenshot_has_none_to_serve(
    auth: TestClient, factory: sessionmaker[Session]
) -> None:
    nid = raise_notification(factory, None)
    assert auth.get(f"/api/notifications/{nid}/screenshot").status_code == 404
    assert auth.get("/api/notifications/999/screenshot").status_code == 404


def test_flagged_orders_list_their_reasons_and_variants(
    auth: TestClient, factory: sessionmaker[Session]
) -> None:
    with factory() as session:
        OrderRepo(session).flag(
            "gid://shopify/Order/1", "#1001", T0 - timedelta(hours=1),
            [FlaggedLine("SKU-1", "stale"), FlaggedLine("SKU-2", "recently_sold_out"),
             FlaggedLine("SKU-3", "stale")], lines_truncated=True, now=T0)
    [order] = auth.get("/api/orders/flagged").json()
    assert (order["order_id"], order["name"]) == ("gid://shopify/Order/1", "#1001")
    assert order["reasons"] == ["stale", "recently_sold_out", "lines_truncated"]
    assert order["variants"] == [{"sku": "SKU-1", "reason": "stale"},
                                 {"sku": "SKU-2", "reason": "recently_sold_out"},
                                 {"sku": "SKU-3", "reason": "stale"}]


def test_workflow_routes_need_a_session(client: TestClient) -> None:
    for url in ("/api/approvals", "/api/notifications", "/api/orders/flagged",
                "/api/notifications/1/screenshot"):
        assert client.get(url).status_code == 401
    assert client.post("/api/approvals/1/approve").status_code == 401
    assert client.post("/api/notifications/1/resolve").status_code == 401
