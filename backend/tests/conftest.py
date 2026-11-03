"""Shared fixtures. The database fixtures need a real Postgres (TEST_DATABASE_URL)."""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session

from alembic import command

BACKEND = Path(__file__).resolve().parent.parent


def alembic_config(url: str) -> Config:
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


@pytest.fixture(scope="session")
def db_engine() -> Iterator[Engine]:
    """A fresh schema built by `alembic upgrade head`, once per test session."""
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.fail(
            "TEST_DATABASE_URL is not set. The database tests need a real Postgres, e.g. "
            "docker run -d --rm -p 55433:5432 -e POSTGRES_PASSWORD=t -e POSTGRES_DB=t postgres:16 "
            "and TEST_DATABASE_URL=postgresql+psycopg://postgres:t@127.0.0.1:55433/t",
            pytrace=False,
        )
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    command.upgrade(alembic_config(url), "head")
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine: Engine) -> Iterator[Session]:
    """A session on the test database; every table is emptied after each test."""
    with Session(db_engine) as session:
        yield session
        session.rollback()
    with db_engine.begin() as conn:
        tables = conn.execute(
            text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname = 'public' AND tablename <> 'alembic_version'"
            )
        ).scalars()
        names = ", ".join(f'"{t}"' for t in tables)
        if names:
            conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
