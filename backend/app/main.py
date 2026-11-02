"""FastAPI application factory.

Not responsible for business rules; routes in `app.api` delegate to services.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import health, login_code
from app.core.config import get_settings
from app.core.database import Database, PostgresDatabase
from app.flows.login_codes import PastedCodeSource


@asynccontextmanager
async def _close_database(app: FastAPI) -> AsyncIterator[None]:
    """Release pooled connections on shutdown, if the database holds any."""
    yield
    database = app.state.database
    if isinstance(database, PostgresDatabase):
        database.engine.dispose()


def create_app(
    database: Database | None = None, pasted_codes: PastedCodeSource | None = None
) -> FastAPI:
    """Build the app. `database` and `pasted_codes` are injectable for tests."""
    if database is None:
        database = PostgresDatabase(get_settings().database_url.get_secret_value())
    app = FastAPI(title="Inventory Sync", lifespan=_close_database)
    app.state.database = database
    app.state.pasted_codes = pasted_codes or PastedCodeSource()
    app.include_router(health.router)
    app.include_router(login_code.router)
    return app
