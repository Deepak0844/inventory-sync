from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from tests.api.conftest import FakeShopify

DEFAULTS = {
    "shopify": {"shop_domain": "", "client_id": "", "has_client_secret": False},
    "mailbox": {"host": "", "user": "", "has_password": False},
    "kill_switch": {"percent": 0.3, "max_flips": 20},
    "sold_out_window_h": 6,
    "order_poll_min": 10,
}


def test_defaults_follow_plan(auth: TestClient) -> None:
    body = auth.get("/api/settings").json()
    assert body["kill_switch"] == DEFAULTS["kill_switch"]
    assert body["sold_out_window_h"] == 6 and body["shopify"]["has_client_secret"] is False


def test_secrets_are_write_only_and_encrypted(
    auth: TestClient, factory: sessionmaker[Session]
) -> None:
    response = auth.put("/api/settings", json={
        "shopify": {"shop_domain": "dev.myshopify.com", "client_id": "cid"},
        "client_secret": "shpss_topsecret", "mailbox": {"host": "imap.example", "user": "codes@x"},
        "mailbox_password": "app-pass-123",
    })
    assert response.status_code == 200
    for text_ in (response.text, auth.get("/api/settings").text):
        assert "shpss_topsecret" not in text_ and "app-pass-123" not in text_
    body = auth.get("/api/settings").json()
    assert body["shopify"] == {"shop_domain": "dev.myshopify.com", "client_id": "cid",
                               "has_client_secret": True}
    assert body["mailbox"] == {"host": "imap.example", "user": "codes@x", "has_password": True}
    with factory() as session:
        raw = session.execute(text("SELECT client_secret_enc, mailbox_password_enc "
                                   "FROM app_settings")).one()
    assert "shpss_topsecret" not in raw[0] and "app-pass-123" not in raw[1]


def test_a_partial_update_keeps_the_rest(auth: TestClient) -> None:
    auth.put("/api/settings", json={"shopify": {"shop_domain": "dev.myshopify.com"},
                                    "client_secret": "s"})
    auth.put("/api/settings", json={"sold_out_window_h": 12})
    body = auth.get("/api/settings").json()
    assert body["sold_out_window_h"] == 12
    assert body["shopify"]["shop_domain"] == "dev.myshopify.com"
    assert body["shopify"]["has_client_secret"] is True


def test_invalid_values_are_rejected(auth: TestClient) -> None:
    for bad in ({"kill_switch": {"percent": 0, "max_flips": 20}},
                {"kill_switch": {"percent": 1.5, "max_flips": 20}},
                {"kill_switch": {"percent": 0.3, "max_flips": 0}},
                {"sold_out_window_h": 0}, {"order_poll_min": 0}):
        assert auth.put("/api/settings", json=bad).status_code == 422, bad


def test_the_shopify_check_uses_the_stored_credentials(
    auth: TestClient, shopify: FakeShopify
) -> None:
    auth.put("/api/settings", json={"shopify": {"shop_domain": "dev.myshopify.com",
                                                "client_id": "cid"}, "client_secret": "sec"})
    result = auth.post("/api/settings/shopify/test").json()
    assert result == {"ok": True, "detail": "Connected to dev-store.myshopify.com"}
    assert shopify.built_with == [("dev.myshopify.com", "cid", "sec")]


def test_the_shopify_check_says_so_when_nothing_is_configured(auth: TestClient) -> None:
    assert auth.post("/api/settings/shopify/test").json() == {
        "ok": False, "detail": "Add the shop domain, client ID and client secret first"}


def test_a_failing_check_reports_without_leaking_the_secret(
    auth: TestClient, shopify: FakeShopify
) -> None:
    auth.put("/api/settings", json={"shopify": {"shop_domain": "d.myshopify.com",
                                                "client_id": "cid"}, "client_secret": "sec-ret-9"})
    shopify.ok = False
    shopify.check = lambda: (_ for _ in ()).throw(RuntimeError("401 for sec-ret-9"))  # type: ignore[method-assign]
    result = auth.post("/api/settings/shopify/test").json()
    assert result["ok"] is False and "sec-ret-9" not in result["detail"]


def test_settings_routes_need_a_session(client: TestClient) -> None:
    assert client.get("/api/settings").status_code == 401
    assert client.put("/api/settings", json={}).status_code == 401
    assert client.post("/api/settings/shopify/test").status_code == 401
