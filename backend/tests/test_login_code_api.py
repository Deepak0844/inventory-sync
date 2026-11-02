from fastapi.testclient import TestClient

from app.flows.login_codes import PastedCodeSource
from app.main import create_app
from tests.test_health import FakeDatabase


def make() -> tuple[TestClient, PastedCodeSource]:
    pasted = PastedCodeSource()
    return TestClient(create_app(database=FakeDatabase(True), pasted_codes=pasted)), pasted


def test_pasting_a_code_hands_it_to_the_waiting_run() -> None:
    client, pasted = make()
    response = client.post("/login-code", json={"code": "654321"})
    assert response.status_code == 202
    assert pasted.poll(0.0) == "654321"


def test_blank_code_is_rejected() -> None:
    client, pasted = make()
    assert client.post("/login-code", json={"code": "  "}).status_code == 422
    assert pasted.poll(0.0) is None
