"""FastAPI application factory.

Not responsible for business rules; routes in `app.api` delegate to services.
"""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI
from sqlalchemy.orm import Session, sessionmaker

from app.api import (
    approvals,
    auth,
    catalog,
    health,
    login_code,
    notifications,
    orders,
    overview,
    settings,
    suppliers,
    test_runs,
)
from app.core.config import get_settings
from app.core.database import Database, PostgresDatabase
from app.core.encryption import SecretBox
from app.services.settings import ShopifyFactory, default_shopify_factory


@asynccontextmanager
async def _close_database(app: FastAPI) -> AsyncIterator[None]:
    """Release pooled connections on shutdown, if the database holds any."""
    yield
    database = app.state.database
    if isinstance(database, PostgresDatabase):
        database.engine.dispose()


def create_app(
    database: Database | None = None,
    session_factory: sessionmaker[Session] | None = None,
    box: SecretBox | None = None,
    now: Callable[[], datetime] | None = None,
    shopify_factory: ShopifyFactory | None = None,
    secure_cookies: bool = True,
    screenshot_dir: Path | None = None,
    data_dir: Path | None = None,
    manual_browser_enabled: bool = False,
    manual_browser_url: str = "http://127.0.0.1:6080/vnc.html?autoconnect=true&resize=scale",
) -> FastAPI:
    """Build the app. Everything outside the process is injectable so tests use fakes.

    Args:
        database: Health probe target. Defaults to Postgres from the settings.
        session_factory: Makes one SQLAlchemy session per request.
        box: Encrypts stored secrets. Defaults to the ENCRYPTION_KEY setting.
        now: The clock. Defaults to the current UTC time.
        shopify_factory: Builds the client for the settings "test connection" check.
        secure_cookies: Mark the session cookie Secure (turn off only for plain-HTTP tests).
        screenshot_dir: The only folder failure screenshots are served from.
        data_dir: Where Test run screenshots and snapshots live (`<data_dir>/test-runs/<id>/`).
    """
    default_data_dir = Path("data")
    if database is None:
        settings_ = get_settings()
        default_data_dir = settings_.data_dir
        postgres = PostgresDatabase(settings_.database_url.get_secret_value())
        database = postgres
        session_factory = session_factory or sessionmaker(postgres.engine, expire_on_commit=False)
        box = box or SecretBox(settings_.encryption_key.get_secret_value())
        manual_browser_enabled = settings_.manual_browser_enabled
        manual_browser_url = settings_.manual_browser_url
    app = FastAPI(title="Inventory Sync", lifespan=_close_database)
    app.state.database = database
    app.state.session_factory = session_factory
    app.state.box = box
    app.state.now = now or (lambda: datetime.now(UTC))
    app.state.shopify_factory = shopify_factory or default_shopify_factory
    app.state.secure_cookies = secure_cookies
    app.state.screenshot_dir = screenshot_dir or Path("data/screenshots")
    app.state.data_dir = data_dir or default_data_dir
    app.state.manual_browser_enabled = manual_browser_enabled
    app.state.manual_browser_url = manual_browser_url
    app.include_router(health.router)
    app.include_router(auth.router)
    for module in (suppliers, login_code, catalog, approvals, notifications, orders, overview,
                   settings, test_runs):
        app.include_router(module.router)
    return app
