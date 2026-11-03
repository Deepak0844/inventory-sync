"""The admin user, dashboard sessions and sign-in throttling.

Not responsible for checking the TOTP code or issuing tokens; the auth service
does. Only token hashes are stored, never the cookie value.
"""

from dataclasses import dataclass
from datetime import datetime

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.encryption import SecretBox
from app.db.models import AdminSession, AdminUser, LoginThrottle

_HASHER = PasswordHasher()


def password_matches(password_hash: str, password: str) -> bool:
    """Return whether `password` matches an argon2 hash (False on any mismatch)."""
    try:
        return _HASHER.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


@dataclass(frozen=True)
class AdminRecord:
    id: int
    username: str
    password_hash: str
    totp_secret: str


class AdminRepo:
    """Rows of the admin tables."""

    def __init__(self, session: Session, box: SecretBox) -> None:
        self._s = session
        self._box = box

    def create_user(self, username: str, password: str, totp_secret: str, now: datetime) -> int:
        """Add the admin with an argon2 password hash and an encrypted TOTP secret."""
        user = AdminUser(username=username, password_hash=_HASHER.hash(password),
                         totp_secret_enc=self._box.encrypt(totp_secret), created_at=now)
        self._s.add(user)
        self._s.commit()
        return user.id

    def get_user(self, username: str) -> AdminRecord | None:
        """Return the admin with their decrypted TOTP secret, or None."""
        user = self._s.scalar(select(AdminUser).where(AdminUser.username == username))
        if user is None:
            return None
        return AdminRecord(user.id, user.username, user.password_hash,
                           self._box.decrypt(user.totp_secret_enc))

    def create_session(self, user_id: int, token_hash: str, now: datetime,
                       expires_at: datetime) -> None:
        """Store a signed-in session by the hash of its token."""
        self._s.add(AdminSession(user_id=user_id, token_hash=token_hash, created_at=now,
                                 expires_at=expires_at))
        self._s.commit()

    def username_for_session(self, token_hash: str, now: datetime) -> str | None:
        """Return the username for an unexpired session, or None."""
        return self._s.scalar(
            select(AdminUser.username).join(AdminSession, AdminSession.user_id == AdminUser.id)
            .where(AdminSession.token_hash == token_hash, AdminSession.expires_at > now))

    def delete_session(self, token_hash: str) -> None:
        """Sign out."""
        self._s.execute(delete(AdminSession).where(AdminSession.token_hash == token_hash))
        self._s.commit()

    def record_failure(self, username: str, now: datetime) -> None:
        """Count a failed sign-in."""
        self._s.add(LoginThrottle(username=username, attempted_at=now))
        self._s.commit()

    def prune_failures(self, before: datetime) -> None:
        """Forget failures older than `before`, so the table cannot grow without bound."""
        self._s.execute(delete(LoginThrottle).where(LoginThrottle.attempted_at < before))
        self._s.commit()

    def failures_since(self, username: str, since: datetime) -> int:
        """Count failed sign-ins for `username` at or after `since`."""
        return self._s.scalar(select(func.count()).where(
            LoginThrottle.username == username, LoginThrottle.attempted_at >= since)) or 0
