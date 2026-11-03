from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.encryption import SecretBox, generate_key
from app.db.models import Job
from app.db.repos.jobs import JobRepo
from app.db.repos.suppliers import SupplierRepo
from app.services.suppliers import queue_action, retry_supplier

NOW = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)
BOX = SecretBox(generate_key())


def supplier(session: Session) -> int:
    return SupplierRepo(session, BOX).create("A", "https://a.example", NOW).id


def count(session: Session, kind: str) -> int:
    return session.scalar(select(func.count()).where(Job.kind == kind)) or 0


def test_pressing_check_now_twice_queues_one_job(db_session: Session) -> None:
    sid = supplier(db_session)
    queue_action(db_session, BOX, NOW, sid, "check_supplier")
    queue_action(db_session, BOX, NOW, sid, "check_supplier")
    assert count(db_session, "check_supplier") == 1


def test_a_login_and_a_check_are_different_jobs(db_session: Session) -> None:
    sid = supplier(db_session)
    queue_action(db_session, BOX, NOW, sid, "login")
    queue_action(db_session, BOX, NOW, sid, "check_supplier")
    assert (count(db_session, "login"), count(db_session, "check_supplier")) == (1, 1)


def test_a_new_job_is_allowed_once_the_earlier_one_has_finished(db_session: Session) -> None:
    sid = supplier(db_session)
    queue_action(db_session, BOX, NOW, sid, "check_supplier")
    job = JobRepo(db_session).claim_next(NOW)
    assert job is not None
    JobRepo(db_session).complete(job.id)
    queue_action(db_session, BOX, NOW, sid, "check_supplier")
    assert count(db_session, "check_supplier") == 2


def test_retry_does_not_add_a_check_when_one_is_already_queued(db_session: Session) -> None:
    sid = supplier(db_session)
    queue_action(db_session, BOX, NOW, sid, "check_supplier")
    SupplierRepo(db_session, BOX).update(sid, paused=True, pause_reason="wrong code")
    retry_supplier(db_session, BOX, NOW, sid)
    assert count(db_session, "check_supplier") == 1
    again = SupplierRepo(db_session, BOX).get(sid)
    assert again is not None and again.paused is False  # the pause is still cleared
