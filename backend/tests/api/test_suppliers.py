from datetime import timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from tests.api.conftest import T0, Clock

NEW = {"name": "Supplier A", "site_url": "https://a.example", "interval_min": 120}


def add(client: TestClient, **over: Any) -> dict[str, Any]:
    response = client.post("/api/suppliers", json={**NEW, **over})
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def test_create_returns_the_supplier_with_plan_defaults(auth: TestClient) -> None:
    s = add(auth)
    assert s["name"] == "Supplier A" and s["stock_source"] == "scrape"
    assert (s["out_confirm_reads"], s["in_confirm_reads"], s["confirm_gap_min"]) == (2, 1, 30)
    assert s["two_fa_methods"] == ["ui_code"] and s["code_window_min"] == 10
    assert s["health"] == "stale" and s["listing_count"] == 0 and s["session_age_s"] is None


def test_list_and_get(auth: TestClient) -> None:
    s = add(auth)
    assert [x["id"] for x in auth.get("/api/suppliers").json()] == [s["id"]]
    assert auth.get(f"/api/suppliers/{s['id']}").json()["name"] == "Supplier A"
    assert auth.get("/api/suppliers/999").status_code == 404


def test_create_validates_the_fields(auth: TestClient) -> None:
    assert auth.post("/api/suppliers", json={"name": "x"}).status_code == 422
    assert auth.post("/api/suppliers", json={**NEW, "interval_min": 0}).status_code == 422
    assert auth.post("/api/suppliers", json={**NEW, "two_fa_methods": ["sms"]}).status_code == 422
    assert auth.post("/api/suppliers", json={**NEW, "max_quantity": 0}).status_code == 422


def test_a_duplicate_name_is_a_conflict(auth: TestClient) -> None:
    add(auth)
    assert auth.post("/api/suppliers", json=NEW).status_code == 409


def test_patch_changes_only_the_given_fields(auth: TestClient) -> None:
    s = add(auth)
    updated = auth.patch(f"/api/suppliers/{s['id']}", json={"interval_min": 60}).json()
    assert updated["interval_min"] == 60 and updated["name"] == "Supplier A"
    assert auth.patch("/api/suppliers/999", json={"interval_min": 60}).status_code == 404


def test_patch_cannot_set_health_or_secrets(auth: TestClient) -> None:
    s = add(auth)
    response = auth.patch(f"/api/suppliers/{s['id']}", json={"paused": True, "password": "x"})
    assert response.status_code == 422


def test_delete(auth: TestClient) -> None:
    s = add(auth)
    assert auth.delete(f"/api/suppliers/{s['id']}").status_code == 204
    assert auth.get(f"/api/suppliers/{s['id']}").status_code == 404


def test_credentials_are_write_only(auth: TestClient, factory: sessionmaker[Session]) -> None:
    s = add(auth)
    url = f"/api/suppliers/{s['id']}/credentials"
    assert auth.get(url).json() == {"username": None, "has_password": False}
    assert auth.put(url, json={"username": "shopper", "password": "s3cr3t-pw"}).status_code == 204
    body = auth.get(url)
    assert body.json() == {"username": "shopper", "has_password": True}
    assert "s3cr3t-pw" not in body.text
    assert "s3cr3t-pw" not in auth.get(f"/api/suppliers/{s['id']}").text
    with factory() as session:
        raw = session.execute(text("SELECT password_enc FROM suppliers")).scalar_one()
    assert "s3cr3t-pw" not in raw


def test_the_flow_is_validated_before_it_is_saved(auth: TestClient) -> None:
    s = add(auth)
    url = f"/api/suppliers/{s['id']}/flow"
    assert auth.get(url).status_code == 404
    bad = auth.put(url, json={"supplier": "a", "version": 1})
    assert bad.status_code == 422
    assert auth.get(url).status_code == 404


def test_a_valid_flow_round_trips(auth: TestClient) -> None:
    from tests.fakes import sample_flow_dict

    s = add(auth)
    url = f"/api/suppliers/{s['id']}/flow"
    assert auth.put(url, json=sample_flow_dict()).status_code == 200
    assert auth.get(url).json()["supplier"] == "supplier-a"


def test_an_invalid_graph_returns_the_validator_message(auth: TestClient) -> None:
    from tests.fakes import sample_flow_dict

    flow = sample_flow_dict()
    flow["edges"].append(["n10", "n2"])
    s = add(auth)
    response = auth.put(f"/api/suppliers/{s['id']}/flow", json=flow)
    assert response.status_code == 422 and "cycle" in response.text


def jobs(factory: sessionmaker[Session]) -> list[tuple[str, int | None]]:
    with factory() as session:
        rows = session.execute(text("SELECT kind, supplier_id FROM jobs ORDER BY id")).all()
    return [(r[0], r[1]) for r in rows]


def test_login_check_and_retry_queue_work_for_the_worker(
    auth: TestClient, factory: sessionmaker[Session]
) -> None:
    s = add(auth)
    base = f"/api/suppliers/{s['id']}"
    assert auth.post(f"{base}/login").status_code == 202
    assert auth.post(f"{base}/check").status_code == 202
    assert jobs(factory) == [("login", s["id"]), ("check_supplier", s["id"])]


def test_retry_clears_a_pause_and_queues_a_check(
    auth: TestClient, factory: sessionmaker[Session]
) -> None:
    s = add(auth)
    with factory() as session:
        session.execute(text("UPDATE suppliers SET paused = true, pause_reason = 'wrong code', "
                             "failed_login_attempts = 2"))
        session.commit()
    assert auth.get(f"/api/suppliers/{s['id']}").json()["health"] == "paused"
    assert auth.post(f"/api/suppliers/{s['id']}/retry").status_code == 202
    after = auth.get(f"/api/suppliers/{s['id']}").json()
    assert after["paused"] is False and after["pause_reason"] is None
    assert jobs(factory) == [("check_supplier", s["id"])]


def test_actions_on_an_unknown_supplier_are_404(auth: TestClient) -> None:
    for action in ("login", "check", "retry"):
        assert auth.post(f"/api/suppliers/999/{action}").status_code == 404


def test_runs_are_listed_newest_first(auth: TestClient, factory: sessionmaker[Session]) -> None:
    from app.db.repos.runs import RunRepo

    s = add(auth)
    with factory() as session:
        repo = RunRepo(session)
        first = repo.start(s["id"], "check", T0)
        repo.finish(first, "ok", "12 listings", T0 + timedelta(minutes=1))
        repo.start(s["id"], "login", T0 + timedelta(minutes=5))
    items = auth.get(f"/api/suppliers/{s['id']}/runs").json()["items"]
    assert [i["kind"] for i in items] == ["login", "check"]
    assert items[1]["summary"] == "12 listings" and items[1]["state"] == "ok"


def test_session_age_and_last_success_are_reported(
    auth: TestClient, factory: sessionmaker[Session], clock: Clock
) -> None:
    s = add(auth)
    with factory() as session:
        session.execute(text("UPDATE suppliers SET session_saved_at = :t, last_success_at = :t"),
                        {"t": T0 - timedelta(hours=2)})
        session.commit()
    body = auth.get(f"/api/suppliers/{s['id']}").json()
    assert body["session_age_s"] == 7200 and body["health"] == "healthy"
