"""FastAPI application factory.

Not responsible for business rules; routes in `app.api` delegate to services.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import health
from app.core.config import get_settings
from app.core.database import Database, PostgresDatabase


@asynccontextmanager
async def _close_database(app: FastAPI) -> AsyncIterator[None]:
    """Release pooled connections on shutdown, if the database holds any."""
    yield
    database = app.state.database
    if isinstance(database, PostgresDatabase):
        database.engine.dispose()


def create_app(database: Database | None = None) -> FastAPI:
    """Build the app. `database` is injectable so tests can use a fake."""
    if database is None:
        database = PostgresDatabase(get_settings().database_url.get_secret_value())
    app = FastAPI(title="Inventory Sync", lifespan=_close_database)
    app.state.database = database
    app.include_router(health.router)
    return app
