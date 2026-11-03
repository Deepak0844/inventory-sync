from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.encryption import SecretBox, generate_key
from app.db.repos.suppliers import SupplierRepo

NOW = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)
BOX = SecretBox(generate_key())


def later(seconds: float) -> datetime:
    return NOW + timedelta(seconds=seconds)


def make_supplier(session: Session, name: str = "Supplier A") -> int:
    return SupplierRepo(session, BOX).create(name=name, site_url="https://a.example", now=NOW).id
