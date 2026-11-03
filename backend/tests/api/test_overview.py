from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.db.repos.approvals import ApprovalRepo, HeldChange
from app.db.repos.catalog import CatalogRepo
from app.db.repos.history import HistoryRepo
from app.db.repos.notifications import NotificationRepo
from app.db.repos.orders import FlaggedLine, OrderRepo
from app.db.repos.states import StateRepo
from tests.api.conftest import T0, Clock


def supplier(auth: TestClient, name: str, interval: int = 120) -> int:
    r = auth.post("/api/suppliers",
                  json={"name": name, "site_url": "https://a.example", "interval_min": interval})
    return int(r.json()["id"])


def seed_success(factory: sessionmaker[Session], sid: int, minutes_ago: float) -> None:
    with factory() as session:
        session.execute(text("UPDATE suppliers SET last_success_at = :t WHERE id = :i"),
                        {"t": T0 - timedelta(minutes=minutes_ago), "i": sid})
        session.commit()


def test_an_empty_system_has_honest_zeros(auth: TestClient) -> None:
    body = auth.get("/api/overview").json()
    assert body["kpis"] == {"sold_out": 0, "in_stock": 0, "stale": 0, "pending": 0}
    assert body["suppliers"] == [] and body["recent_changes"] == []
    assert len(body["sold_out_by_day"]) == 14 and body["updated_at"].startswith("2026-11-03T12:00")
    assert auth.get("/api/banner").json() == {
        "red_strip": [], "counts": {"approvals": 0, "orders": 0, "notifications": 0}}


def test_kpis_count_variants_by_state_stale_and_pending(
    auth: TestClient, factory: sessionmaker[Session]
) -> None:
    sid = supplier(auth, "Supplier A", interval=60)
    with factory() as session:
        catalog = CatalogRepo(session)
        states = StateRepo(session)
        ids = [catalog.upsert_variant(f"gid://{s}", s, s) for s in ("A", "B", "C", "D")]
        states.save_variant_state(ids[0], "sold_out", T0, 0)
        states.save_variant_state(ids[1], "available", T0, 100)
        states.save_variant_state(ids[2], "available", T0, 100)
        ApprovalRepo(session).create(sid, [HeldChange(ids[0], "available", "sold_out", 0)], T0)
    kpis = auth.get("/api/overview").json()["kpis"]
    assert kpis == {"sold_out": 1, "in_stock": 2, "stale": 4, "pending": 1}


def test_recent_changes_come_newest_first(
    auth: TestClient, factory: sessionmaker[Session]
) -> None:
    with factory() as session:
        vid = CatalogRepo(session).upsert_variant("gid://A", "A", "A")
        history = HistoryRepo(session)
        history.record_change(vid, None, "available", "first_sync", "auto", T0 - timedelta(hours=2))
        history.record_change(vid, "available", "sold_out", "all_out_of_stock", "auto",
                              T0 - timedelta(hours=1))
    changes = auth.get("/api/overview").json()["recent_changes"]
    assert [(c["sku"], c["from_state"], c["to_state"], c["reason"]) for c in changes] == [
        ("A", "available", "sold_out", "all_out_of_stock"), ("A", None, "available", "first_sync")]


def test_sold_out_by_day_follows_the_change_history(
    auth: TestClient, factory: sessionmaker[Session]
) -> None:
    with factory() as session:
        vid = CatalogRepo(session).upsert_variant("gid://A", "A", "A")
        HistoryRepo(session).record_change(vid, None, "sold_out", "r", "auto",
                                           T0 - timedelta(days=1, hours=1))
    days = auth.get("/api/overview").json()["sold_out_by_day"]
    assert [d["count"] for d in days][-3:] == [0, 1, 1] and days[0]["count"] == 0


def test_supplier_health_is_listed(auth: TestClient, factory: sessionmaker[Session]) -> None:
    sid = supplier(auth, "Supplier A")
    seed_success(factory, sid, 10)
    [s] = auth.get("/api/overview").json()["suppliers"]
    assert (s["id"], s["name"], s["health"]) == (sid, "Supplier A", "healthy")


def test_the_red_strip_names_suppliers_past_twice_their_interval(
    auth: TestClient, factory: sessionmaker[Session], clock: Clock
) -> None:
    late = supplier(auth, "Late", interval=60)
    ok = supplier(auth, "Fine", interval=60)
    never = supplier(auth, "New", interval=60)
    seed_success(factory, late, 121)
    seed_success(factory, ok, 119)
    strip = auth.get("/api/banner").json()["red_strip"]
    assert [(r["supplier_id"], r["supplier_name"]) for r in strip] == [(late, "Late")]
    assert never and strip[0]["last_success_at"].startswith("2026-11-03T09:59")


def test_banner_counts_what_needs_action(
    auth: TestClient, factory: sessionmaker[Session]
) -> None:
    sid = supplier(auth, "Supplier A")
    with factory() as session:
        vid = CatalogRepo(session).upsert_variant("gid://A", "A", "A")
        ApprovalRepo(session).create(sid, [HeldChange(vid, "available", "sold_out", 0)], T0)
        OrderRepo(session).flag("o1", "#1", T0, [FlaggedLine("A", "stale")], False, T0)
        notes = NotificationRepo(session)
        notes.add("flow_failure", sid, "x", T0)
        done = notes.add("blocked", sid, "y", T0)
        notes.resolve(done, T0)
    assert auth.get("/api/banner").json()["counts"] == {
        "approvals": 1, "orders": 1, "notifications": 1}


def test_overview_routes_need_a_session(client: TestClient) -> None:
    assert client.get("/api/overview").status_code == 401
    assert client.get("/api/banner").status_code == 401
