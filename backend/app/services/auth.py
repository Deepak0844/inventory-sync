"""Admin sign-in: password plus TOTP, server-side sessions, throttling.

Not responsible for cookies or HTTP status codes; the route maps the exceptions.
Only a hash of the session token is stored, so a database leak cannot be replayed.
"""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

import pyotp
from argon2 import PasswordHasher
from sqlalchemy.orm import Session

from app.core.encryption import SecretBox
from app.db.repos.admin import AdminRepo, password_matches

SESSION_TTL = timedelta(hours=12)
THROTTLE_WINDOW = timedelta(minutes=15)
MAX_FAILURES = 5
# Verified against when the username is unknown, so a miss costs the same time as a hit.
_DUMMY_HASH = PasswordHasher().hash("not-a-real-password")


class SignInFailed(Exception):
    """Wrong username, password or code. Deliberately says which one nowhere."""


class TooManyAttempts(Exception):
    """Too many recent failures for this username."""


@dataclass(frozen=True)
class AdminSetup:
    """What the owner needs to add the account to an authenticator app."""

    totp_secret: str
    otpauth_uri: str


def hash_token(token: str) -> str:
    """Return the SHA-256 hex digest stored in place of the session token."""
    return hashlib.sha256(token.encode()).hexdigest()


def sign_in(
    session: Session, box: SecretBox, now: datetime, username: str, password: str, totp: str
) -> str:
    """Check the password and code and open a session.

    Args:
        session: Database session.
        box: Decrypts the stored TOTP secret.
        now: Current time.
        username: As typed.
        password: As typed. Never logged or echoed.
        totp: The 6-digit code. The previous 30-second step is accepted for clock drift.

    Returns:
        The new session token (give it to the browser; only its hash is stored).

    Raises:
        TooManyAttempts: after 5 failures for the username in 15 minutes, even if this
            attempt would have been right.
        SignInFailed: for any wrong part.
    """
    repo = AdminRepo(session, box)
    if repo.failures_since(username, now - THROTTLE_WINDOW) >= MAX_FAILURES:
        raise TooManyAttempts
    user = repo.get_user(username)
    password_ok = password_matches(user.password_hash if user else _DUMMY_HASH, password)
    code_ok = user is not None and pyotp.TOTP(user.totp_secret).verify(
        totp, for_time=now, valid_window=1
    )
    if user is None or not (password_ok and code_ok):
        repo.record_failure(username, now)
        raise SignInFailed
    token = secrets.token_urlsafe(32)
    repo.create_session(user.id, hash_token(token), now, now + SESSION_TTL)
    return token


def username_for(session: Session, box: SecretBox, token: str, now: datetime) -> str | None:
    """Return the username for an unexpired session token, or None."""
    return AdminRepo(session, box).username_for_session(hash_token(token), now)


def sign_out(session: Session, box: SecretBox, token: str) -> None:
    """End the session for `token` (a no-op if it is unknown)."""
    AdminRepo(session, box).delete_session(hash_token(token))


def create_admin(
    session: Session, box: SecretBox, username: str, password: str, now: datetime
) -> AdminSetup:
    """Create the admin with a fresh TOTP secret. Shown once; only the encrypted secret is kept."""
    secret = pyotp.random_base32()
    AdminRepo(session, box).create_user(username, password, secret, now)
    uri = pyotp.TOTP(secret).provisioning_uri(name=username, issuer_name="Inventory Sync")
    return AdminSetup(secret, uri)
