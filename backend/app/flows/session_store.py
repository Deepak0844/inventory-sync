"""Encrypted storage for a Supplier's saved browser session (cookies).

Not responsible for deciding whether a session is still valid.
"""

from typing import Protocol

from app.core.encryption import SecretBox


class TextRepository(Protocol):
    """One text value kept somewhere durable (a database column, later)."""

    def get(self) -> str | None:
        """Return the stored text, or None."""
        ...

    def put(self, value: str | None) -> None:
        """Store `value`, or clear it when None."""
        ...


class MemoryTextRepository:
    """In-memory repository for tests and local runs."""

    def __init__(self) -> None:
        self._value: str | None = None

    def get(self) -> str | None:
        """Return the stored text, or None."""
        return self._value

    def put(self, value: str | None) -> None:
        """Store `value`, or clear it when None."""
        self._value = value


class EncryptedSessionStore:
    """Saves cookies encrypted, so they are never in plain text at rest."""

    def __init__(self, box: SecretBox, repository: TextRepository) -> None:
        self._box = box
        self._repository = repository

    def load(self) -> str | None:
        """Return the saved cookies JSON, or None if no session is saved.

        Raises:
            DecryptionError: if the stored value cannot be decrypted.
        """
        token = self._repository.get()
        return None if token is None else self._box.decrypt(token)

    def save(self, cookies_json: str) -> None:
        """Encrypt and store the cookies."""
        self._repository.put(self._box.encrypt(cookies_json))

    def clear(self) -> None:
        """Forget the saved session."""
        self._repository.put(None)
