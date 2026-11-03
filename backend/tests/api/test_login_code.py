from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.core.encryption import SecretBox
from app.db.repos.codes import PastedCodeRepo
from tests.api.conftest import T0, Clock


def supplier(auth: TestClient, name: str = "Supplier A") -> int:
    r = auth.post("/api/suppliers",
                  json={"name": name, "site_url": "https://a.example", "interval_min": 120})
    return int(r.json()["id"])


def wait(factory: sessionmaker[Session], supplier_id: int, minutes: float) -> None:
    with factory() as session:
        session.execute(text("UPDATE suppliers SET waiting_for_code_until = :t WHERE id = :i"),
                        {"t": T0 + timedelta(minutes=minutes), "i": supplier_id})
        session.commit()


def test_nothing_is_pending_when_no_supplier_waits(auth: TestClient) -> None:
    supplier(auth)
    assert auth.get("/api/login-code/pending").json() == []


def test_a_waiting_supplier_is_listed_with_its_deadline(
    auth: TestClient, factory: sessionmaker[Session]
) -> None:
    sid = supplier(auth)
    wait(factory, sid, 7)
    pending = auth.get("/api/login-code/pending").json()
    assert [(p["supplier_id"], p["supplier_name"]) for p in pending] == [(sid, "Supplier A")]
    assert pending[0]["expires_at"].startswith("2026-11-03T12:07")


def test_an_expired_prompt_is_no_longer_pending(
    auth: TestClient, factory: sessionmaker[Session], clock: Clock
) -> None:
    sid = supplier(auth)
    wait(factory, sid, 7)
    clock.advance(minutes=8)
    assert auth.get("/api/login-code/pending").json() == []


def test_a_pasted_code_is_stored_for_the_waiting_run(
    auth: TestClient, factory: sessionmaker[Session], box: SecretBox
) -> None:
    sid = supplier(auth)
    wait(factory, sid, 7)
    response = auth.post(f"/api/suppliers/{sid}/login-code", json={"code": " 123456 "})
    assert response.status_code == 202
    with factory() as session:
        record = PastedCodeRepo(session, box).take(sid)
    assert record is not None and record.code == "123456"


def test_a_code_for_a_supplier_that_is_not_waiting_is_404_and_not_kept(
    auth: TestClient, factory: sessionmaker[Session], box: SecretBox
) -> None:
    sid = supplier(auth)
    body = {"code": "123456"}
    assert auth.post(f"/api/suppliers/{sid}/login-code", json=body).status_code == 404
    assert auth.post("/api/suppliers/999/login-code", json=body).status_code == 404
    with factory() as session:
        assert PastedCodeRepo(session, box).take(sid) is None


def test_a_blank_code_is_rejected(auth: TestClient, factory: sessionmaker[Session]) -> None:
    sid = supplier(auth)
    wait(factory, sid, 7)
    assert auth.post(f"/api/suppliers/{sid}/login-code", json={"code": "  "}).status_code == 422


def test_the_old_unauthenticated_route_is_gone(client: TestClient) -> None:
    assert client.post("/login-code", json={"code": "123456"}).status_code == 404


def test_pasting_needs_a_session(client: TestClient) -> None:
    assert client.post("/api/suppliers/1/login-code", json={"code": "123456"}).status_code == 401
