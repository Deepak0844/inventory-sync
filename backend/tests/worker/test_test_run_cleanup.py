from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

from app.db.repos.jobs import JobRecord
from app.db.repos.test_runs import FlowTestRunRepo
from app.worker.summary import handle_daily_summary
from tests.worker.conftest import World


def make_run(w: World, root: Path, age_days: float) -> int:
    run_id = FlowTestRunRepo(w.session).create(w.supplier_id, "login", {}, w.now() - timedelta(
        days=age_days))
    folder = root / "test-runs" / str(run_id)
    folder.mkdir(parents=True)
    (folder / "step-1.png").write_bytes(b"png")
    return run_id


def test_the_daily_job_deletes_test_runs_and_files_older_than_seven_days(
    make_world: Callable[..., World], tmp_path: Path
) -> None:
    w = make_world(variants=1)
    w.deps.data_dir = tmp_path
    old, fresh = make_run(w, tmp_path, 8), make_run(w, tmp_path, 6)
    with w.deps.session_factory() as session:
        handle_daily_summary(w.deps, session, JobRecord(1, "daily_summary", None, {}, 0))
    repo = FlowTestRunRepo(w.session)
    w.session.expire_all()
    assert repo.get(old) is None and not (tmp_path / "test-runs" / str(old)).exists()
    assert repo.get(fresh) is not None and (tmp_path / "test-runs" / str(fresh)).exists()


def test_a_missing_folder_does_not_stop_the_cleanup(
    make_world: Callable[..., World], tmp_path: Path
) -> None:
    w = make_world(variants=1)
    w.deps.data_dir = tmp_path
    old = FlowTestRunRepo(w.session).create(w.supplier_id, "login", {},
                                            w.now() - timedelta(days=9))
    with w.deps.session_factory() as session:
        handle_daily_summary(w.deps, session, JobRecord(1, "daily_summary", None, {}, 0))
    w.session.expire_all()
    assert FlowTestRunRepo(w.session).get(old) is None
