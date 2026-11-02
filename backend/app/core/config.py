"""Application settings read from the environment (and a local .env in development).

Not responsible for building the database engine or the encryption box.
"""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Missing required values fail at startup, not mid-run."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    # SecretStr keeps the key out of reprs and logs.
    encryption_key: SecretStr


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings, loading them on first use.

    Raises:
        pydantic.ValidationError: if a required variable is missing.
    """
    return Settings()
