from datetime import timedelta

import pyotp
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.encryption import SecretBox, generate_key
from app.db.repos.admin import AdminRepo
from app.services.auth import THROTTLE_WINDOW, SignInFailed, create_admin, sign_in
from tests.api.conftest import T0

BOX = SecretBox(generate_key())


def test_the_created_admin_can_sign_in_with_the_secret_that_was_shown(db_session: Session) -> None:
    setup = create_admin(db_session, BOX, "owner", "a-long-enough-password", T0)
    code = pyotp.TOTP(setup.totp_secret).at(T0)
    assert sign_in(db_session, BOX, T0, "owner", "a-long-enough-password", code)


def test_the_authenticator_link_names_the_account(db_session: Session) -> None:
    setup = create_admin(db_session, BOX, "owner", "a-long-enough-password", T0)
    assert setup.otpauth_uri.startswith("otpauth://totp/") and "owner" in setup.otpauth_uri
    assert setup.totp_secret in setup.otpauth_uri


def test_neither_the_password_nor_the_totp_secret_is_stored_in_plain_text(
    db_session: Session,
) -> None:
    setup = create_admin(db_session, BOX, "owner", "a-long-enough-password", T0)
    row = db_session.execute(text("SELECT password_hash, totp_secret_enc FROM admin_users")).one()
    assert "a-long-enough-password" not in row[0]
    assert setup.totp_secret not in row[1]


def test_a_wrong_code_does_not_sign_in(db_session: Session) -> None:
    create_admin(db_session, BOX, "owner", "a-long-enough-password", T0)
    with pytest.raises(SignInFailed):
        sign_in(db_session, BOX, T0, "owner", "a-long-enough-password", "000000")


def test_an_unknown_username_still_checks_a_code_so_timing_matches(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    real = pyotp.TOTP.verify

    def spy(self: pyotp.TOTP, otp: str, *args: object, **kwargs: object) -> bool:
        calls.append(otp)
        return real(self, otp, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(pyotp.TOTP, "verify", spy)
    with pytest.raises(SignInFailed):
        sign_in(db_session, BOX, T0, "nobody", "whatever-password", "123456")
    assert calls == ["123456"]


def test_old_failures_are_pruned_when_a_new_one_is_recorded(db_session: Session) -> None:
    create_admin(db_session, BOX, "owner", "a-long-enough-password", T0)
    repo = AdminRepo(db_session, BOX)
    for _ in range(3):
        repo.record_failure("ghost", T0 - THROTTLE_WINDOW - timedelta(minutes=1))
    with pytest.raises(SignInFailed):
        sign_in(db_session, BOX, T0, "owner", "wrong-password-here", "000000")
    assert repo.failures_since("ghost", T0 - timedelta(days=1)) == 0
    assert repo.failures_since("owner", T0 - THROTTLE_WINDOW) == 1
