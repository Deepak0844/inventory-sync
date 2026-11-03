import threading
import time
from collections.abc import Callable, Sequence
from datetime import timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.db.repos.codes import PastedCodeRepo
from app.db.repos.jobs import JobRecord
from app.db.repos.suppliers import SessionCookiesRepo, SupplierRepo
from app.db.repos.test_runs import FlowTestRunRecord, FlowTestRunRepo
from app.flows.definition import FlowDefinition
from app.flows.page import PageError
from app.worker.jobs import serve
from app.worker.test_run import _WaitingCodes, handle_test_run, masked_selectors
from tests.fakes import BrokenPage, sample_flow_dict
from tests.test_flow_observer import with_branch
from tests.worker.conftest import BASE, World
from tests.worker.test_login import RIGHT, LoginSite, logged_out_world

GUARDED = ("listing_states", "variant_states", "readings", "inventory_changes", "notifications",
           "approvals", "approval_changes", "flagged_orders")


def snapshot_of_world(w: World) -> dict[str, Any]:
    counts = {t: w.session.execute(text(f"SELECT count(*) FROM {t}")).scalar() for t in GUARDED}
    s = SupplierRepo(w.session, w.box).get(w.supplier_id)
    assert s is not None
    return {**counts, "paused": s.paused, "failed": s.failed_login_attempts, "blocked": s.blocked,
            "last_success": s.last_success_at}


def no_shopify(settings: object, secrets: object) -> None:
    raise AssertionError("a Test run must never reach Shopify")


def start(w: World, tmp_path: Path, mode: str = "login", **request: Any) -> FlowTestRunRecord:
    w.deps.data_dir = tmp_path
    w.deps.shopify = no_shopify
    body = {"supplier_id": w.supplier_id, "mode": mode, **request}
    repo = FlowTestRunRepo(w.session)
    run_id = repo.create(w.supplier_id, mode, body, w.now())
    with w.deps.session_factory() as session:
        handle_test_run(w.deps, session, JobRecord(1, "test_run", w.supplier_id,
                                                   {"test_run_id": run_id}, 0))
    w.session.expire_all()
    run = FlowTestRunRepo(w.session).get(run_id)
    assert run is not None
    return run


def logged_out(make_world: Callable[..., World], **fields: object) -> tuple[World, LoginSite]:
    """A logged-out Supplier with the right code already pasted; also returns the site's page."""
    site = LoginSite()
    w = logged_out_world(make_world, site, **fields)
    PastedCodeRepo(w.session, w.box).submit(w.supplier_id, RIGHT, w.now())
    return w, site


def test_a_login_test_run_records_a_masked_screenshot_for_every_node(
    make_world: Callable[..., World], tmp_path: Path
) -> None:
    w, _ = logged_out(make_world)
    run = start(w, tmp_path)
    assert run.state == "done" and run.login_result == "logged_in"
    assert [s["node_id"] for s in run.steps] == [f"n{i}" for i in range(1, 11)]
    assert all(s["ok"] and s["error"] is None for s in run.steps)
    first = run.steps[0]["screenshot_url"]
    assert first == f"/api/test-runs/{run.id}/files/step-1.png"
    assert (tmp_path / "test-runs" / str(run.id) / "step-1.png").read_bytes() == b"png"


def test_every_screenshot_masks_passwords_and_codes(
    make_world: Callable[..., World], tmp_path: Path
) -> None:
    w, site = logged_out(make_world)
    start(w, tmp_path)
    assert site.screenshots
    assert all({"input[type=password]", "#password", "#otp"} <= set(m) for m in site.screenshots)


def test_a_test_run_changes_nothing_and_never_reaches_shopify(
    make_world: Callable[..., World], tmp_path: Path
) -> None:
    w, _ = logged_out(make_world)
    before = snapshot_of_world(w)
    start(w, tmp_path)
    start(w, tmp_path, mode="extract", listing_url=f"{BASE}/p/1")
    assert snapshot_of_world(w) == before
    assert w.shopify.writes == []


def test_a_wrong_code_is_reported_but_does_not_count_or_pause(
    make_world: Callable[..., World], tmp_path: Path
) -> None:
    w = logged_out_world(make_world, LoginSite())
    PastedCodeRepo(w.session, w.box).submit(w.supplier_id, "000000", w.now())
    before = snapshot_of_world(w)
    run = start(w, tmp_path)
    assert run.state == "failed" and run.login_result == "wrong_code"
    assert "wrong_code" in (run.error or "")
    assert snapshot_of_world(w) == before


def test_a_run_that_needed_a_code_that_never_came_ends_without_pausing(
    make_world: Callable[..., World], tmp_path: Path
) -> None:
    w = logged_out_world(make_world, LoginSite(), code_window_min=1)
    states: list[str] = []
    real_sleep = w.clock.sleep

    def watch(seconds: float) -> None:
        run = FlowTestRunRepo(w.session)
        w.session.expire_all()
        open_run = run.open_for_supplier(w.supplier_id, w.now())
        if open_run is not None:
            states.append(open_run.state)
        real_sleep(seconds)

    w.clock.sleep = watch  # type: ignore[method-assign]
    before = snapshot_of_world(w)
    run = start(w, tmp_path)
    assert "waiting_for_code" in states
    assert run.state == "failed" and run.login_result == "code_timeout"
    assert snapshot_of_world(w) == before
    supplier = SupplierRepo(w.session, w.box).get(w.supplier_id)
    assert supplier is not None and supplier.waiting_for_code_until is None


def test_up_to_a_node_stops_there_and_snapshots_the_page(
    make_world: Callable[..., World], tmp_path: Path
) -> None:
    w, site = logged_out(make_world)
    site.html = (
        '<form><input id="email" value="owner"><input type="password" id="password" '
        'value="s3cret-pw"><button id="go">Go</button></form><script>x()</script>'
    )
    run = start(w, tmp_path, up_to_node_id="n4")
    assert [s["node_id"] for s in run.steps] == ["n1", "n2", "n3", "n4"]
    assert run.state == "done" and run.login_result == "stopped_after_node"
    assert run.snapshot == {"screenshot_url": f"/api/test-runs/{run.id}/files/snapshot.png",
                            "html_url": f"/api/test-runs/{run.id}/files/snapshot.html"}
    html = (tmp_path / "test-runs" / str(run.id) / "snapshot.html").read_text()
    assert 'id="email"' in html and "s3cret-pw" not in html and "<script" not in html


def test_the_stored_session_is_not_reused_when_stopping_at_a_node_and_is_left_untouched(
    make_world: Callable[..., World], tmp_path: Path
) -> None:
    w = make_world(variants=1)  # starts with a saved, working session
    stored = SessionCookiesRepo(w.session, w.supplier_id, w.now).get()
    run = start(w, tmp_path, up_to_node_id="n2")
    assert [s["node_id"] for s in run.steps] == ["n1", "n2"]
    w.session.expire_all()
    assert SessionCookiesRepo(w.session, w.supplier_id, w.now).get() == stored


def test_a_saved_working_session_is_reused_without_steps(
    make_world: Callable[..., World], tmp_path: Path
) -> None:
    w = make_world(variants=1)
    run = start(w, tmp_path)
    assert run.state == "done" and run.login_result == "session_reused" and run.steps == []
    assert run.snapshot is not None


def test_extract_mode_reports_the_reading_and_the_rule_that_matched(
    make_world: Callable[..., World], tmp_path: Path
) -> None:
    w = make_world(variants=1)
    w.set_stock("In stock")
    run = start(w, tmp_path, mode="extract", listing_url=f"{BASE}/p/1")
    assert run.state == "done"
    assert run.reading == {"result": "in_stock", "error_kind": None, "quantity": None,
                           "matched_rule": "in_stock_if"}
    assert run.snapshot is not None


def test_a_changed_page_is_an_unknown_reading_not_a_failed_run(
    make_world: Callable[..., World], tmp_path: Path
) -> None:
    w = make_world(variants=1)
    w.set_stock(None)  # the stock element is gone
    run = start(w, tmp_path, mode="extract", listing_url=f"{BASE}/p/1")
    assert run.state == "done"
    assert run.reading is not None
    assert (run.reading["result"], run.reading["error_kind"]) == ("unknown", "flow_failure")


def test_an_unsaved_draft_flow_is_what_runs(
    make_world: Callable[..., World], tmp_path: Path
) -> None:
    w = make_world(variants=1)
    w.set_stock("Gone for good")
    draft = sample_flow_dict()
    draft["extract"]["out_of_stock_if"] = {"contains": "Gone for good"}
    run = start(w, tmp_path, mode="extract", listing_url=f"{BASE}/p/1", flow=draft)
    assert run.reading is not None and run.reading["result"] == "out_of_stock"
    saved = start(w, tmp_path, mode="extract", listing_url=f"{BASE}/p/1")
    assert saved.reading is not None and saved.reading["result"] == "unknown"


def test_a_failed_screenshot_leaves_the_step_without_one_and_the_run_continues(
    make_world: Callable[..., World], tmp_path: Path
) -> None:
    w, site = logged_out(make_world)

    def broken(masks: Sequence[str]) -> bytes:
        raise PageError("no screenshot")

    site.screenshot = broken  # type: ignore[assignment,method-assign]
    run = start(w, tmp_path)
    assert run.state == "done"
    assert all(s["screenshot_url"] is None for s in run.steps)
    assert run.snapshot is None


def test_missing_credentials_fail_the_run_with_a_clear_message(
    make_world: Callable[..., World], tmp_path: Path
) -> None:
    w = make_world(variants=1)
    w.session.execute(text("UPDATE suppliers SET username_enc = NULL, password_enc = NULL"))
    w.session.commit()
    run = start(w, tmp_path)
    assert run.state == "failed" and "credentials" in (run.error or "").lower()


def test_a_crash_in_the_browser_fails_the_run_without_a_traceback_in_the_error(
    make_world: Callable[..., World], tmp_path: Path
) -> None:
    w = make_world(variants=1)
    w.page.__class__ = BrokenPage  # type: ignore[assignment]
    run = start(w, tmp_path)
    assert run.state == "failed"
    assert "s3cret" not in (run.error or "") and "Traceback" not in (run.error or "")


def test_a_rerun_after_a_worker_died_starts_the_steps_over(
    make_world: Callable[..., World], tmp_path: Path
) -> None:
    w, _ = logged_out(make_world)
    repo = FlowTestRunRepo(w.session)
    run_id = repo.create(w.supplier_id, "login", {"supplier_id": w.supplier_id, "mode": "login"},
                         w.now())
    repo.set_state(run_id, "running")
    repo.add_step(run_id, {"node_id": "stale"})
    w.deps.data_dir = tmp_path
    with w.deps.session_factory() as session:
        handle_test_run(w.deps, session, JobRecord(1, "test_run", w.supplier_id,
                                                   {"test_run_id": run_id}, 1))
    w.session.expire_all()
    run = repo.get(run_id)
    assert run is not None and "stale" not in [s["node_id"] for s in run.steps]


def test_a_finished_run_is_not_run_again(
    make_world: Callable[..., World], tmp_path: Path
) -> None:
    w, _ = logged_out(make_world)
    repo = FlowTestRunRepo(w.session)
    run_id = repo.create(w.supplier_id, "login", {"supplier_id": w.supplier_id, "mode": "login"},
                         w.now())
    repo.finish(run_id, "done", w.now(), login_result="logged_in")
    w.deps.data_dir = tmp_path
    with w.deps.session_factory() as session:
        handle_test_run(w.deps, session, JobRecord(1, "test_run", w.supplier_id,
                                                   {"test_run_id": run_id}, 0))
    w.session.expire_all()
    run = repo.get(run_id)
    assert run is not None and run.steps == []


def test_a_full_login_test_run_does_not_save_cookies_to_the_suppliers_real_session(
    make_world: Callable[..., World], tmp_path: Path
) -> None:
    w, _ = logged_out(make_world)  # no saved session; the flow's save_session node will run
    run = start(w, tmp_path)
    assert run.login_result == "logged_in"
    w.session.expire_all()
    assert SessionCookiesRepo(w.session, w.supplier_id, w.now).get() is None


# --- review fixes -----------------------------------------------------------------------


def test_secret_fills_are_masked_whether_or_not_the_mask_flag_is_set() -> None:
    data = sample_flow_dict()
    data["nodes"][2]["mask"] = False  # the password fill
    masks = masked_selectors(FlowDefinition.model_validate(data))
    assert {"input[type=password]", "#password", "#otp"} <= set(masks)
    assert "#email" not in masks  # the username is not a secret


def test_screenshots_mask_the_password_field_even_without_the_flag(
    make_world: Callable[..., World], tmp_path: Path
) -> None:
    w, site = logged_out(make_world)
    draft = sample_flow_dict()
    draft["nodes"][2]["mask"] = False
    start(w, tmp_path, flow=draft)
    assert site.screenshots
    assert all({"input[type=password]", "#password", "#otp"} <= set(m) for m in site.screenshots)


def test_the_run_goes_back_to_running_as_soon_as_the_code_arrives(
    make_world: Callable[..., World],
) -> None:
    w = logged_out_world(make_world, LoginSite())
    supplier = SupplierRepo(w.session, w.box).get(w.supplier_id)
    assert supplier is not None
    repo = FlowTestRunRepo(w.session)
    run_id = repo.create(w.supplier_id, "login", {}, w.now())
    repo.set_state(run_id, "running")
    codes = _WaitingCodes(w.deps, w.session, supplier, repo, run_id)

    def state() -> str:
        w.session.expire_all()
        run = repo.get(run_id)
        assert run is not None
        return run.state

    assert codes.poll(0.0) is None
    assert state() == "waiting_for_code"
    PastedCodeRepo(w.session, w.box).submit(w.supplier_id, RIGHT, w.now())
    assert codes.poll(0.0) == RIGHT
    assert state() == "running"


def test_a_stop_node_the_walk_never_reaches_fails_the_run_with_no_snapshot(
    make_world: Callable[..., World], tmp_path: Path
) -> None:
    w, _ = logged_out(make_world)  # no #banner on the page, so the branch takes "no"
    draft = sample_flow_dict()
    with_branch(draft)
    run = start(w, tmp_path, flow=draft, up_to_node_id="dismiss")
    assert run.state == "failed" and run.login_result == "flow_failure"
    assert run.error == "That step was not reached on this path (check the branch)."
    assert run.snapshot is None
    assert [s["node_id"] for s in run.steps][:3] == ["n1", "b", "n2"]


def test_a_real_step_failure_before_the_stop_node_is_not_reported_as_unreachable(
    make_world: Callable[..., World], tmp_path: Path
) -> None:
    w = logged_out_world(make_world, LoginSite(password_ok=False))
    run = start(w, tmp_path, up_to_node_id="n8")
    assert run.state == "failed" and run.login_result == "bad_credentials"
    assert "not reached" not in (run.error or "")


def test_the_worker_loop_fails_a_run_that_never_finished(
    make_world: Callable[..., World],
) -> None:
    w = make_world(variants=1)
    dead = FlowTestRunRepo(w.session).create(
        w.supplier_id, "login", {}, w.now() - timedelta(minutes=31))
    stop = threading.Event()
    thread = threading.Thread(target=serve, args=(w.deps, stop, 30.0, 0.01), daemon=True)
    thread.start()
    try:
        deadline = time.time() + 10
        state = "queued"
        while time.time() < deadline and state == "queued":
            time.sleep(0.05)
            w.session.expire_all()
            run = FlowTestRunRepo(w.session).get(dead)
            state = run.state if run else "gone"
        assert state == "failed"
        final = FlowTestRunRepo(w.session).get(dead)
        assert final is not None and final.error == "The test run did not finish."
    finally:
        stop.set()
        thread.join(timeout=5)


def test_a_snapshot_before_any_login_step_runs_without_credentials(
    make_world: Callable[..., World], tmp_path: Path
) -> None:
    w, site = logged_out(make_world)
    w.session.execute(text("UPDATE suppliers SET username_enc = NULL, password_enc = NULL"))
    w.session.commit()
    site.html = '<form><input id="email"></form>'
    run = start(w, tmp_path, up_to_node_id="n1")
    assert run.state == "done" and run.login_result == "stopped_after_node"
    assert run.snapshot is not None


def test_a_step_with_no_selector_yet_does_not_break_the_screenshots() -> None:
    # The starting outline has blank selectors on its Fill steps; a blank mask makes
    # Playwright refuse the screenshot, which used to drop the whole snapshot.
    from app.flows.definition import FlowDefinition
    from app.worker.test_run import masked_selectors
    from tests.fakes import sample_flow_dict

    data = sample_flow_dict()
    data["nodes"][2]["selector"] = ""
    masks = masked_selectors(FlowDefinition.model_validate(data))
    assert "" not in masks and "input[type=password]" in masks and "#otp" in masks
