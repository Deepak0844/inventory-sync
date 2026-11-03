"""Fixtures for API tests: real app and test database, a fixed clock, a signed-in client."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.encryption import SecretBox, generate_key
from app.db.repos.admin import AdminRepo
from app.main import create_app
from tests.test_health import FakeDatabase

T0 = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)
PASSWORD = "correct horse battery"
TOTP_SECRET = pyotp.random_base32()


class Clock:
    """A settable clock so tests control sessions, throttling and staleness."""

    def __init__(self) -> None:
        self.at = T0

    def __call__(self) -> datetime:
        return self.at

    def advance(self, **kwargs: float) -> None:
        self.at += timedelta(**kwargs)


class FakeShopify:
    """Stands in for the Shopify client factory; records what it was built with."""

    def __init__(self, ok: bool = True) -> None:
        self.ok = ok
        self.built_with: list[tuple[str, str, str]] = []

    def __call__(self, shop: str, client_id: str, client_secret: str) -> "FakeShopify":
        self.built_with.append((shop, client_id, client_secret))
        return self

    def check(self) -> str:
        if not self.ok:
            raise RuntimeError("bad credentials for shop")
        return "Connected to dev-store.myshopify.com"


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def box() -> SecretBox:
    return SecretBox(generate_key())


@pytest.fixture
def shopify() -> FakeShopify:
    return FakeShopify()


@pytest.fixture
def screenshots(tmp_path: Path) -> Path:
    folder = tmp_path / "screenshots"
    folder.mkdir()
    return folder


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    folder = tmp_path / "data"
    folder.mkdir()
    return folder


@pytest.fixture
def factory(db_session: Session) -> sessionmaker[Session]:
    engine = db_session.get_bind()
    assert isinstance(engine, Engine)
    return sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
def make_client(
    factory: sessionmaker[Session], box: SecretBox, clock: Clock, shopify: FakeShopify,
    screenshots: Path, data_dir: Path,
) -> Callable[[], TestClient]:
    def build() -> TestClient:
        app = create_app(database=FakeDatabase(True), session_factory=factory, box=box,
                         now=clock, shopify_factory=shopify, secure_cookies=False,
                         screenshot_dir=screenshots, data_dir=data_dir)
        return TestClient(app)

    return build


@pytest.fixture
def client(make_client: Callable[[], TestClient]) -> TestClient:
    """Not signed in."""
    return make_client()


@pytest.fixture
def admin(factory: sessionmaker[Session], box: SecretBox, clock: Clock) -> str:
    with factory() as session:
        AdminRepo(session, box).create_user("owner", PASSWORD, TOTP_SECRET, clock())
    return "owner"


def sign_in_body(at: datetime = T0, **overrides: Any) -> dict[str, str]:
    """A correct sign-in body for time `at` (the app verifies against the test clock)."""
    body = {"username": "owner", "password": PASSWORD, "totp": pyotp.TOTP(TOTP_SECRET).at(at)}
    return {**body, **overrides}


@pytest.fixture
def auth(client: TestClient, admin: str) -> TestClient:
    """Signed in as the admin."""
    response = client.post("/api/auth/login", json=sign_in_body())
    assert response.status_code == 204, response.text
    return client
