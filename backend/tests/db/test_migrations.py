from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Engine, inspect

from app.db.models import Base

EXPECTED = {
    "admin_users", "admin_sessions", "login_throttle", "suppliers", "listings", "variants",
    "mappings", "listing_states", "variant_states", "readings", "inventory_changes", "runs",
    "jobs", "notifications", "approvals", "approval_changes", "flagged_orders",
    "flagged_order_lines", "app_settings", "pasted_codes",
}


def test_migration_creates_every_table(db_engine: Engine) -> None:
    assert EXPECTED <= set(inspect(db_engine).get_table_names())


def test_models_and_migrations_agree(db_engine: Engine) -> None:
    with db_engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []
