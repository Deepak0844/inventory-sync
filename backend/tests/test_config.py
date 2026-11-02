import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.encryption import generate_key


def test_settings_load_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    key = generate_key()
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@db/x")
    monkeypatch.setenv("ENCRYPTION_KEY", key)
    settings = Settings(_env_file=None)
    assert settings.database_url.endswith("/x")
    assert settings.encryption_key.get_secret_value() == key


def test_missing_encryption_key_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@db/x")
    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_repr_hides_encryption_key(monkeypatch: pytest.MonkeyPatch) -> None:
    key = generate_key()
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@db/x")
    monkeypatch.setenv("ENCRYPTION_KEY", key)
    assert key not in repr(Settings(_env_file=None))
