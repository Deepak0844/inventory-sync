from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.repos.test_runs import FlowTestRunRepo
from tests.db.helpers import NOW, later, make_supplier

REQUEST = {"supplier_id": 1, "mode": "login"}


def test_a_new_run_is_queued_with_its_request(db_session: Session) -> None:
    supplier = make_supplier(db_session)
    repo = FlowTestRunRepo(db_session)
    run = repo.get(repo.create(supplier, "login", REQUEST, NOW))
    assert run is not None
    assert (run.state, run.mode, run.request, run.steps) == ("queued", "login", REQUEST, [])
    assert run.snapshot is None and run.reading is None and run.finished_at is None


def test_unknown_run_is_none(db_session: Session) -> None:
    assert FlowTestRunRepo(db_session).get(99) is None


def test_steps_are_appended_in_order(db_session: Session) -> None:
    supplier = make_supplier(db_session)
    repo = FlowTestRunRepo(db_session)
    run_id = repo.create(supplier, "login", REQUEST, NOW)
    repo.add_step(run_id, {"node_id": "n1", "ok": True})
    repo.add_step(run_id, {"node_id": "n2", "ok": False})
    run = repo.get(run_id)
    assert run is not None
    assert [s["node_id"] for s in run.steps] == ["n1", "n2"]


def test_finish_stores_the_outcome(db_session: Session) -> None:
    supplier = make_supplier(db_session)
    repo = FlowTestRunRepo(db_session)
    run_id = repo.create(supplier, "extract", REQUEST, NOW)
    repo.finish(run_id, "done", later(3), snapshot={"screenshot": "snapshot.png"},
                reading={"result": "in_stock"}, login_result="logged_in", error=None)
    run = repo.get(run_id)
    assert run is not None
    assert run.state == "done" and run.finished_at == later(3)
    assert run.snapshot == {"screenshot": "snapshot.png"} and run.reading == {"result": "in_stock"}
    assert run.login_result == "logged_in"


def test_only_an_unfinished_run_counts_as_open(db_session: Session) -> None:
    supplier = make_supplier(db_session)
    repo = FlowTestRunRepo(db_session)
    assert repo.open_for_supplier(supplier, NOW) is None
    run_id = repo.create(supplier, "login", REQUEST, NOW)
    for state in ("queued", "running", "waiting_for_code"):
        repo.set_state(run_id, state)
        open_run = repo.open_for_supplier(supplier, NOW)
        assert open_run is not None and open_run.id == run_id
    repo.finish(run_id, "done", later(1))
    assert repo.open_for_supplier(supplier, NOW) is None


def test_open_run_is_per_supplier(db_session: Session) -> None:
    a, b = make_supplier(db_session, "A"), make_supplier(db_session, "B")
    repo = FlowTestRunRepo(db_session)
    repo.create(a, "login", REQUEST, NOW)
    assert repo.open_for_supplier(b, NOW) is None


def test_old_runs_are_deleted_and_their_ids_returned(db_session: Session) -> None:
    supplier = make_supplier(db_session)
    repo = FlowTestRunRepo(db_session)
    old = repo.create(supplier, "login", REQUEST, NOW)
    new = repo.create(supplier, "login", REQUEST, later(10 * 86400))
    gone = repo.delete_older_than(later(8 * 86400))
    assert gone == [old]
    assert repo.get(old) is None and repo.get(new) is not None


def test_deleting_a_supplier_deletes_its_test_runs(db_session: Session) -> None:
    supplier = make_supplier(db_session)
    repo = FlowTestRunRepo(db_session)
    run_id = repo.create(supplier, "login", REQUEST, NOW)
    db_session.execute(text("DELETE FROM suppliers WHERE id = :i"), {"i": supplier})
    db_session.commit()
    assert repo.get(run_id) is None


def test_a_run_open_for_over_30_minutes_no_longer_counts_as_open(db_session: Session) -> None:
    supplier = make_supplier(db_session)
    repo = FlowTestRunRepo(db_session)
    repo.create(supplier, "login", REQUEST, NOW)
    assert repo.open_for_supplier(supplier, later(29 * 60)) is not None
    assert repo.open_for_supplier(supplier, later(31 * 60)) is None


def test_reaping_fails_runs_open_for_over_30_minutes_and_leaves_the_rest(
    db_session: Session,
) -> None:
    supplier = make_supplier(db_session)
    repo = FlowTestRunRepo(db_session)
    dead = repo.create(supplier, "login", REQUEST, NOW)
    repo.set_state(dead, "waiting_for_code")
    fresh = repo.create(supplier, "login", REQUEST, later(25 * 60))
    done = repo.create(supplier, "login", REQUEST, NOW)
    repo.finish(done, "done", later(60))
    assert repo.reap_stale(later(31 * 60)) == [dead]
    reaped = repo.get(dead)
    assert reaped is not None and reaped.state == "failed"
    assert reaped.error == "The test run did not finish." and reaped.finished_at == later(31 * 60)
    fresh_run, done_run = repo.get(fresh), repo.get(done)
    assert fresh_run is not None and fresh_run.state == "queued"
    assert done_run is not None and done_run.state == "done" and done_run.error is None
    assert repo.reap_stale(later(32 * 60)) == []
