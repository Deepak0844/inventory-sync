from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.repos.admin import AdminRepo, password_matches
from app.db.repos.codes import PastedCodeRepo
from app.db.repos.settings import SettingsRepo
from tests.db.helpers import BOX, NOW, later, make_supplier


def test_admin_password_is_hashed_and_totp_secret_is_encrypted(db_session: Session) -> None:
    repo = AdminRepo(db_session, BOX)
    repo.create_user("owner", "correct horse", "JBSWY3DPEHPK3PXP", NOW)
    user = repo.get_user("owner")
    assert user is not None and user.totp_secret == "JBSWY3DPEHPK3PXP"
    assert password_matches(user.password_hash, "correct horse")
    assert not password_matches(user.password_hash, "wrong")
    raw = db_session.execute(
        text("SELECT password_hash || totp_secret_enc FROM admin_users")).scalar()
    assert "correct horse" not in str(raw) and "JBSWY3DPEHPK3PXP" not in str(raw)


def test_unknown_admin_is_none(db_session: Session) -> None:
    assert AdminRepo(db_session, BOX).get_user("nobody") is None


def test_session_lookup_expiry_and_logout(db_session: Session) -> None:
    repo = AdminRepo(db_session, BOX)
    user_id = repo.create_user("owner", "pw", "S", NOW)
    repo.create_session(user_id, "hash-1", NOW, later(3600))
    assert repo.username_for_session("hash-1", later(10)) == "owner"
    assert repo.username_for_session("hash-1", later(7200)) is None
    assert repo.username_for_session("nope", NOW) is None
    repo.delete_session("hash-1")
    assert repo.username_for_session("hash-1", later(10)) is None


def test_failed_sign_ins_are_counted_inside_the_window_only(db_session: Session) -> None:
    repo = AdminRepo(db_session, BOX)
    repo.record_failure("owner", NOW)
    repo.record_failure("owner", later(600))
    repo.record_failure("other", later(600))
    assert repo.failures_since("owner", NOW) == 2
    assert repo.failures_since("owner", later(300)) == 1


def test_settings_start_with_the_plan_defaults(db_session: Session) -> None:
    s = SettingsRepo(db_session, BOX).get()
    assert (s.kill_switch_percent, s.kill_switch_max_flips, s.sold_out_window_h) == (0.30, 20, 6)
    assert not s.has_client_secret and not s.has_mailbox_password


def test_settings_secrets_are_encrypted_and_not_returned(db_session: Session) -> None:
    repo = SettingsRepo(db_session, BOX)
    repo.update(shop_domain="dev.myshopify.com", client_secret="shpss_secret",
                mailbox_password="app-pass", sold_out_window_h=12)
    s = repo.get()
    assert s.shop_domain == "dev.myshopify.com" and s.has_client_secret and s.has_mailbox_password
    assert s.sold_out_window_h == 12
    assert "shpss_secret" not in repr(s)
    secrets = repo.get_secrets()
    assert (secrets.client_secret, secrets.mailbox_password) == ("shpss_secret", "app-pass")
    raw = db_session.execute(
        text("SELECT client_secret_enc || mailbox_password_enc FROM app_settings")).scalar()
    assert "shpss_secret" not in str(raw) and "app-pass" not in str(raw)


def test_updating_without_a_secret_keeps_the_stored_one(db_session: Session) -> None:
    repo = SettingsRepo(db_session, BOX)
    repo.update(client_secret="keep-me")
    repo.update(shop_domain="x.myshopify.com")
    assert repo.get_secrets().client_secret == "keep-me"


def test_pasted_code_is_taken_once_and_stored_encrypted(db_session: Session) -> None:
    supplier = make_supplier(db_session)
    repo = PastedCodeRepo(db_session, BOX)
    repo.submit(supplier, "654321", NOW)
    raw = db_session.execute(text("SELECT code_enc FROM pasted_codes")).scalar()
    assert "654321" not in str(raw)
    taken = repo.take(supplier)
    assert taken is not None and (taken.code, taken.submitted_at) == ("654321", NOW)
    assert repo.take(supplier) is None


def test_the_latest_pasted_code_wins_and_older_ones_are_dropped(db_session: Session) -> None:
    supplier = make_supplier(db_session)
    repo = PastedCodeRepo(db_session, BOX)
    repo.submit(supplier, "111111", NOW)
    repo.submit(supplier, "222222", later(5))
    taken = repo.take(supplier)
    assert taken is not None and taken.code == "222222"
    assert repo.take(supplier) is None
