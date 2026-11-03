"""Alembic environment: reads the URL from the config, else from the app settings."""

from sqlalchemy import create_engine

from alembic import context
from app.db.models import Base

config = context.config
target_metadata = Base.metadata


def _url() -> str:
    url = config.get_main_option("sqlalchemy.url")
    if url:
        return url.replace("%%", "%")
    from app.core.config import get_settings

    return get_settings().database_url.get_secret_value()


def run_migrations_online() -> None:
    engine = create_engine(_url())
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


run_migrations_online()
