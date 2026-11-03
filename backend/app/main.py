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
    """
    if database is None:
        settings_ = get_settings()
        postgres = PostgresDatabase(settings_.database_url.get_secret_value())
        database = postgres
        session_factory = session_factory or sessionmaker(postgres.engine, expire_on_commit=False)
        box = box or SecretBox(settings_.encryption_key.get_secret_value())
    app = FastAPI(title="Inventory Sync", lifespan=_close_database)
    app.state.database = database
    app.state.session_factory = session_factory
    app.state.box = box
    app.state.now = now or (lambda: datetime.now(UTC))
    app.state.shopify_factory = shopify_factory or default_shopify_factory
    app.state.secure_cookies = secure_cookies
    app.state.screenshot_dir = screenshot_dir or Path("data/screenshots")
    app.include_router(health.router)
    app.include_router(auth.router)
    for module in (suppliers, login_code, catalog, approvals, notifications, orders, overview,
                   settings):
        app.include_router(module.router)
    return app
