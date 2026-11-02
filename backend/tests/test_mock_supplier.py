import re

import pytest
from fastapi.testclient import TestClient

from mock_supplier.app import MockState, create_mock_app


@pytest.fixture
def state() -> MockState:
    return MockState(code_generator=lambda: "123456", clock=lambda: 1000.0)


@pytest.fixture
def client(state: MockState) -> TestClient:
    return TestClient(create_mock_app(state), follow_redirects=False)


def log_in(client: TestClient, code: str = "123456") -> None:
    client.post("/login", data={"username": "shop", "password": "pw"})
    client.get("/verify")
    client.post("/verify", data={"code": code})


def test_wrong_password_is_rejected(client: TestClient) -> None:
    response = client.post("/login", data={"username": "shop", "password": "nope"})
    assert response.status_code == 401


def test_correct_password_asks_for_the_code(client: TestClient) -> None:
    response = client.post("/login", data={"username": "shop", "password": "pw"})
    assert response.status_code == 303
    assert response.headers["location"] == "/verify"
    assert "Enter the code" in client.get("/verify").text


def test_requesting_the_code_emails_it(client: TestClient) -> None:
    client.post("/login", data={"username": "shop", "password": "pw"})
    client.get("/verify")
    mail = client.get("/_control/outbox").json()
    assert mail == [{"sender": "no-reply@mock-supplier.test", "body": "Your code is 123456",
                     "sent_at": 1000.0}]


def test_correct_code_shows_the_logged_in_marker(client: TestClient) -> None:
    log_in(client)
    assert 'data-testid="account-menu"' in client.get("/account").text


def test_wrong_code_does_not_log_in(client: TestClient) -> None:
    log_in(client, code="000000")
    assert 'data-testid="account-menu"' not in client.get("/account").text


def test_product_page_requires_a_session(client: TestClient) -> None:
    response = client.get("/product/1")
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_stock_can_be_flipped(client: TestClient) -> None:
    log_in(client)
    assert re.search(r'id="stock">In stock<', client.get("/product/1").text)
    client.post("/_control/stock/1", json={"in_stock": False})
    assert re.search(r'id="stock">Out of stock<', client.get("/product/1").text)


def test_removed_page_is_404(client: TestClient) -> None:
    log_in(client)
    client.post("/_control/remove/1")
    assert client.get("/product/1").status_code == 404


def test_changed_selector_renames_the_stock_element(client: TestClient) -> None:
    log_in(client)
    client.post("/_control/selector", json={"changed": True})
    page = client.get("/product/1").text
    assert 'id="stock"' not in page
    assert 'id="availability"' in page


def test_captcha_switch_blocks_the_login(client: TestClient) -> None:
    client.post("/_control/captcha", json={"on": True})
    response = client.post("/login", data={"username": "shop", "password": "pw"})
    assert "CAPTCHA" in response.text


def test_email_delay_holds_the_mail_back(client: TestClient, state: MockState) -> None:
    client.post("/_control/email_delay", json={"seconds": 30})
    client.post("/login", data={"username": "shop", "password": "pw"})
    client.get("/verify")
    assert client.get("/_control/outbox").json() == []
    state.clock = lambda: 1031.0
    assert len(client.get("/_control/outbox").json()) == 1
