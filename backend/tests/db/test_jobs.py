import threading

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.db.repos.jobs import JobRepo
from tests.db.helpers import NOW, later


def test_due_jobs_are_claimed_in_run_after_order(db_session: Session) -> None:
    jobs = JobRepo(db_session)
    late = jobs.enqueue("check", None, {}, later(20), NOW)
    early = jobs.enqueue("check", None, {}, later(10), NOW)
    assert jobs.claim_next(later(5)) is None
    first = jobs.claim_next(later(30))
    second = jobs.claim_next(later(30))
    assert first is not None and second is not None
    assert (first.id, second.id) == (early, late)
    assert jobs.claim_next(later(30)) is None


def test_claim_marks_the_job_running_and_carries_the_payload(db_session: Session) -> None:
    jobs = JobRepo(db_session)
    jobs.enqueue("login", None, {"why": "button"}, NOW, NOW)
    job = jobs.claim_next(NOW)
    assert job is not None
    assert (job.kind, job.payload, job.attempts) == ("login", {"why": "button"}, 0)


def test_two_sessions_never_claim_the_same_job(db_engine: Engine, db_session: Session) -> None:
    for _ in range(20):
        JobRepo(db_session).enqueue("check", None, {}, NOW, NOW)
    claimed: list[int] = []

    def worker() -> None:
        with Session(db_engine) as session:
            while (job := JobRepo(session).claim_next(NOW)) is not None:
                claimed.append(job.id)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(claimed) == sorted(set(claimed)) and len(claimed) == 20


def test_a_failed_job_is_retried_later(db_session: Session) -> None:
    jobs = JobRepo(db_session)
    job_id = jobs.enqueue("check", None, {}, NOW, NOW)
    jobs.claim_next(NOW)
    jobs.fail(job_id, NOW, "boom", retry_after_s=60, max_attempts=3)
    assert jobs.claim_next(later(30)) is None
    retry = jobs.claim_next(later(61))
    assert retry is not None and retry.attempts == 1


def test_a_job_that_keeps_failing_is_given_up_on(db_session: Session) -> None:
    jobs = JobRepo(db_session)
    job_id = jobs.enqueue("check", None, {}, NOW, NOW)
    for i in range(2):
        jobs.claim_next(later(1000 * i))
        jobs.fail(job_id, later(1000 * i), "boom", retry_after_s=0, max_attempts=2)
    assert jobs.claim_next(later(10_000)) is None


def test_completed_job_is_not_claimed_again(db_session: Session) -> None:
    jobs = JobRepo(db_session)
    job_id = jobs.enqueue("check", None, {}, NOW, NOW)
    jobs.claim_next(NOW)
    jobs.complete(job_id)
    assert jobs.claim_next(later(100)) is None


def test_stale_running_job_is_requeued(db_session: Session) -> None:
    jobs = JobRepo(db_session)
    job_id = jobs.enqueue("check", None, {}, NOW, NOW)
    jobs.claim_next(NOW)  # worker dies here
    assert jobs.requeue_stale(later(10), older_than_s=60) == 0
    assert jobs.requeue_stale(later(120), older_than_s=60) == 1
    again = jobs.claim_next(later(120))
    assert again is not None and again.id == job_id
