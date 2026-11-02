"""FastAPI application factory.

Not responsible for business rules; routes in `app.api` delegate to services.
"""

from fastapi import FastAPI

from app.api import health
from app.core.config import get_settings
from app.core.database import Database, PostgresDatabase


def create_app(database: Database | None = None) -> FastAPI:
    """Build the app. `database` is injectable so tests can use a fake."""
    app = FastAPI(title="Inventory Sync")
    app.state.database = database or PostgresDatabase(get_settings().database_url)
    app.include_router(health.router)
    return app
