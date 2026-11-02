"""Symmetric encryption for Supplier credentials and sessions at rest.

Not responsible for deciding what gets encrypted or where ciphertext is stored.
"""

from cryptography.fernet import Fernet, InvalidToken


class DecryptionError(Exception):
    """Raised when a ciphertext cannot be decrypted with the configured key."""


def generate_key() -> str:
    """Return a new random key, suitable for the ENCRYPTION_KEY setting."""
    return Fernet.generate_key().decode()


class SecretBox:
    """Encrypts and decrypts short secrets with a Fernet key (authenticated)."""

    def __init__(self, key: str) -> None:
        """Build a box from a urlsafe base64 Fernet key.

        Raises:
            ValueError: if the key is not a valid Fernet key.
        """
        self._fernet = Fernet(key.encode())

    def encrypt(self, plaintext: str) -> str:
        """Return the ciphertext of `plaintext` as text safe to store in a column."""
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, token: str) -> str:
        """Return the plaintext for `token`.

        Raises:
            DecryptionError: if the token is corrupt or was made with another key.
        """
        try:
            return self._fernet.decrypt(token.encode()).decode()
        except InvalidToken as exc:
            raise DecryptionError("ciphertext does not match the encryption key") from exc
