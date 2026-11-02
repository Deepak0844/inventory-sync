from fastapi.testclient import TestClient

from app.main import create_app


class FakeDatabase:
    def __init__(self, ok: bool) -> None:
        self.ok = ok

    def ping(self) -> bool:
        return self.ok


def client_for(ok: bool) -> TestClient:
    return TestClient(create_app(database=FakeDatabase(ok)))


def test_health_is_ok_when_database_answers() -> None:
    response = client_for(True).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "up"}


def test_health_is_503_when_database_is_down() -> None:
    response = client_for(False).get("/health")
    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "database": "down"}


def test_falsy_injected_database_is_still_used() -> None:
    class FalsyDatabase(FakeDatabase):
        def __bool__(self) -> bool:
            return False

    client = TestClient(create_app(database=FalsyDatabase(True)))
    assert client.get("/health").status_code == 200
