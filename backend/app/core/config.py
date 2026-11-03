"""Application settings read from the environment (and a local .env in development).

Not responsible for building the database engine or the encryption box.
"""

from functools import lru_cache
from pathlib import Path

from cryptography.fernet import Fernet
from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Missing required values fail at startup, not mid-run."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # SecretStr because the URL embeds the Postgres password.
    database_url: SecretStr
    # SecretStr keeps the key out of reprs and logs.
    encryption_key: SecretStr
    # Where Test run screenshots and snapshots are kept (see docs/api.md, Test runs).
    data_dir: Path = Path("data")

    @field_validator("encryption_key")
    @classmethod
    def _key_must_be_a_fernet_key(cls, value: SecretStr) -> SecretStr:
        """Reject a malformed key at startup instead of at the first encryption."""
        try:
            Fernet(value.get_secret_value().encode())
        except ValueError as exc:
            raise ValueError("ENCRYPTION_KEY is not a valid Fernet key") from exc
        return value


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings, loading them on first use.

    Raises:
        pydantic.ValidationError: if a required variable is missing.
    """
    return Settings()
