from collections.abc import Callable
from datetime import timedelta

import pyotp
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from tests.api.conftest import PASSWORD, TOTP_SECRET, Clock, sign_in_body


def test_health_needs_no_sign_in(client: TestClient) -> None:
    assert client.get("/health").status_code == 200


def test_api_routes_need_a_session(client: TestClient) -> None:
    assert client.get("/api/suppliers").status_code == 401
    assert client.get("/api/auth/me").status_code == 401


def test_sign_in_sets_an_httponly_strict_cookie(client: TestClient, admin: str) -> None:
    response = client.post("/api/auth/login", json=sign_in_body())
    assert response.status_code == 204
    cookie = response.headers["set-cookie"].lower()
    assert "session=" in cookie and "httponly" in cookie and "samesite=strict" in cookie


def test_me_returns_the_username_once_signed_in(auth: TestClient) -> None:
    assert auth.get("/api/auth/me").json() == {"username": "owner"}


def test_logout_ends_the_session(auth: TestClient) -> None:
    assert auth.post("/api/auth/logout").status_code == 204
    assert auth.get("/api/auth/me").status_code == 401


def test_session_expires(auth: TestClient, clock: Clock) -> None:
    clock.advance(hours=13)
    assert auth.get("/api/auth/me").status_code == 401


def test_only_a_token_hash_is_stored(
    auth: TestClient, factory: sessionmaker[Session]
) -> None:
    from sqlalchemy import text

    token = auth.cookies.get("session")
    assert token
    with factory() as session:
        stored = session.execute(text("SELECT token_hash FROM admin_sessions")).scalar_one()
    assert stored != token and token not in stored


def test_wrong_password_wrong_code_and_unknown_user_look_the_same(
    client: TestClient, admin: str
) -> None:
    bad = [
        sign_in_body(password="nope"),
        sign_in_body(totp="000000"),
        sign_in_body(username="ghost"),
    ]
    responses = [client.post("/api/auth/login", json=b) for b in bad]
    assert {r.status_code for r in responses} == {401}
    assert {r.text for r in responses} == {'{"detail":"Sign in failed"}'}


def test_the_previous_totp_step_is_accepted_for_clock_drift(
    client: TestClient, admin: str, clock: Clock
) -> None:
    previous = pyotp.TOTP(TOTP_SECRET).at(clock() - timedelta(seconds=30))
    assert client.post("/api/auth/login", json=sign_in_body(totp=previous)).status_code == 204


def test_five_failures_in_fifteen_minutes_block_even_the_right_password(
    client: TestClient, admin: str, clock: Clock
) -> None:
    for _ in range(5):
        assert client.post("/api/auth/login", json=sign_in_body(password="x")).status_code == 401
    assert client.post("/api/auth/login", json=sign_in_body()).status_code == 429
    clock.advance(minutes=16)
    assert client.post("/api/auth/login", json=sign_in_body(at=clock())).status_code == 204


def test_the_password_is_never_echoed(client: TestClient, admin: str) -> None:
    response = client.post("/api/auth/login", json=sign_in_body(password="wrong-one-123"))
    assert "wrong-one-123" not in response.text


def test_another_client_does_not_share_the_session(
    auth: TestClient, make_client: Callable[[], TestClient]
) -> None:
    assert make_client().get("/api/auth/me").status_code == 401
    assert auth.get("/api/auth/me").status_code == 200
    assert PASSWORD
