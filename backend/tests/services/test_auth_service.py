import pyotp
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.encryption import SecretBox, generate_key
from app.services.auth import SignInFailed, create_admin, sign_in
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
