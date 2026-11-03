from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.repos.suppliers import SessionCookiesRepo, SupplierRepo
from app.flows.session_store import EncryptedSessionStore
from tests.db.helpers import BOX, NOW


def test_create_applies_the_plan_defaults(db_session: Session) -> None:
    s = SupplierRepo(db_session, BOX).create(name="A", site_url="https://a.example", now=NOW)
    assert (s.interval_min, s.out_confirm_reads, s.in_confirm_reads, s.confirm_gap_min) == (
        180, 2, 1, 30)
    assert not s.paused and not s.has_password


def test_credentials_round_trip_and_are_encrypted_at_rest(db_session: Session) -> None:
    repo = SupplierRepo(db_session, BOX)
    s = repo.create(name="A", site_url="https://a.example", now=NOW)
    repo.set_credentials(s.id, "owner@example.com", "hunter2")
    creds = repo.get_credentials(s.id)
    assert creds is not None
    assert (creds.username, creds.password) == ("owner@example.com", "hunter2")
    raw = db_session.execute(text("SELECT username_enc || password_enc FROM suppliers")).scalar()
    assert "hunter2" not in str(raw) and "owner@example.com" not in str(raw)
    record = repo.get(s.id)
    assert record is not None and record.has_password and record.username == "owner@example.com"
    assert "hunter2" not in repr(record)


def test_credentials_are_none_until_set(db_session: Session) -> None:
    repo = SupplierRepo(db_session, BOX)
    s = repo.create(name="A", site_url="https://a.example", now=NOW)
    assert repo.get_credentials(s.id) is None


def test_update_changes_only_the_given_fields(db_session: Session) -> None:
    repo = SupplierRepo(db_session, BOX)
    s = repo.create(name="A", site_url="https://a.example", now=NOW)
    updated = repo.update(s.id, interval_min=60, paused=True, pause_reason="two wrong codes")
    assert (updated.interval_min, updated.paused, updated.name) == (60, True, "A")


def test_flow_json_round_trips(db_session: Session) -> None:
    repo = SupplierRepo(db_session, BOX)
    s = repo.create(name="A", site_url="https://a.example", now=NOW)
    assert repo.get_flow(s.id) is None
    repo.set_flow(s.id, {"supplier": "a", "version": 1})
    assert repo.get_flow(s.id) == {"supplier": "a", "version": 1}


def test_session_cookies_repo_plugs_into_the_encrypted_session_store(
    db_session: Session,
) -> None:
    s = SupplierRepo(db_session, BOX).create(name="A", site_url="https://a.example", now=NOW)
    store = EncryptedSessionStore(BOX, SessionCookiesRepo(db_session, s.id, lambda: NOW))
    assert store.load() is None
    store.save('[{"name": "session", "value": "abc"}]')
    assert store.load() == '[{"name": "session", "value": "abc"}]'
    raw = db_session.execute(text("SELECT session_cookies_enc FROM suppliers")).scalar()
    assert "abc" not in str(raw)
    store.clear()
    assert store.load() is None


def test_delete_removes_the_supplier(db_session: Session) -> None:
    repo = SupplierRepo(db_session, BOX)
    s = repo.create(name="A", site_url="https://a.example", now=NOW)
    repo.delete(s.id)
    assert repo.get(s.id) is None and repo.list() == []


