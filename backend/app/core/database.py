"""Database access: the engine and a small health probe.

Not responsible for models or queries; those live with the modules that own them.
"""

from typing import Protocol

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError


class Database(Protocol):
    """What the API needs from the database layer, so tests can pass a fake."""

    def ping(self) -> bool:
        """Return True if the database answers a trivial query."""
        ...


class PostgresDatabase:
    """Postgres-backed implementation of `Database`."""

    def __init__(self, url: str) -> None:
        self.engine: Engine = create_engine(
            url, pool_pre_ping=True, connect_args={"connect_timeout": 3}
        )

    def ping(self) -> bool:
        """Return True if `SELECT 1` succeeds; a failure is reported, not raised."""
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except SQLAlchemyError:
            return False
        return True
