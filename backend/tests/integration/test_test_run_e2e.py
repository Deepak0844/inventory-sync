"""Test runs end to end: real Chromium, the mock Supplier, a real Postgres and a Shopify that
fails the test if anything touches it."""

import base64
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest
from playwright.sync_api import Browser
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.clock import SystemClock
from app.core.encryption import SecretBox, generate_key
from app.db.repos.jobs import JobRecord
from app.db.repos.suppliers import SupplierRepo
from app.db.repos.test_runs import FlowTestRunRecord, FlowTestRunRepo
from app.flows.playwright_session import PlaywrightSupplierSession
from app.mail.codes import MailMessage
from app.worker.deps import Deps
from app.worker.test_run import handle_test_run
from tests.integration.conftest import RunningMock, mock_flow_json

GUARDED = ("listing_states", "variant_states", "readings", "inventory_changes", "notifications",
           "approvals", "flagged_orders")
MASK_PIXELS = """async (b64) => {
  const img = new Image(); img.src = 'data:image/png;base64,' + b64; await img.decode();
  const c = document.createElement('canvas'); c.width = img.width; c.height = img.height;
  const x = c.getContext('2d'); x.drawImage(img, 0, 0);
  const d = x.getImageData(0, 0, c.width, c.height).data; let n = 0;
  for (let i = 0; i < d.length; i += 4) if (d[i] > 240 && d[i+1] < 16 && d[i+2] > 240) n++;
  return n;
}"""


def no_shopify(settings: object, secrets: object) -> None:
    raise AssertionError("a Test run must never reach Shopify")


@dataclass
class Lab:
    session: Session
    deps: Deps
    mock: RunningMock
    browser: Browser
    supplier_id: int
    folder: Path

    def run(self, mode: str = "login", **request: object) -> FlowTestRunRecord:
        repo = FlowTestRunRepo(self.session)
        body = {"supplier_id": self.supplier_id, "mode": mode, **request}
        run_id = repo.create(self.supplier_id, mode, body, datetime.now(UTC))
        with self.deps.session_factory() as s:
            handle_test_run(self.deps, s, JobRecord(1, "test_run", self.supplier_id,
                                                    {"test_run_id": run_id}, 0))
        self.session.expire_all()
        run = repo.get(run_id)
        assert run is not None
        return run

    def png(self, run: FlowTestRunRecord, step: int) -> bytes:
        return (self.folder / "test-runs" / str(run.id) / f"step-{step}.png").read_bytes()

    def mask_pixels(self, png: bytes) -> int:
        page = self.browser.new_page()
        try:
            return int(page.evaluate(MASK_PIXELS, base64.b64encode(png).decode()))
        finally:
            page.close()

    def table_counts(self) -> dict[str, object]:
        return {t: self.session.execute(text(f"SELECT count(*) FROM {t}")).scalar()
                for t in GUARDED}


@pytest.fixture
def lab(db_session: Session, db_engine: Engine, browser: Browser, mock_supplier: RunningMock,
        tmp_path: Path) -> Lab:
    box = SecretBox(generate_key())

    def fetch() -> Sequence[MailMessage]:
        return [MailMessage(str(m["sender"]), str(m["body"]), float(m["sent_at"]))  # type: ignore[arg-type]
                for m in mock_supplier.outbox()]

    deps = Deps(
        session_factory=sessionmaker(bind=db_engine), box=box, clock=SystemClock(),
        browser=lambda: PlaywrightSupplierSession(browser), shopify=no_shopify,
        mail=lambda settings, secrets: fetch, poll_s=0.1, data_dir=tmp_path)
    suppliers = SupplierRepo(db_session, box)
    sid = suppliers.create("Mock Supplier", mock_supplier.base_url, datetime.now(UTC),
                           two_fa_methods=["email_code"]).id
    suppliers.set_credentials(sid, "shop", "pw")
    suppliers.set_flow(sid, json.loads(mock_flow_json(mock_supplier.base_url)))
    return Lab(db_session, deps, mock_supplier, browser, sid, tmp_path)


def test_a_login_test_run_walks_every_node_with_real_screenshots(lab: Lab) -> None:
    run = lab.run()
    assert run.state == "done" and run.login_result == "logged_in", run.error
    assert [s["node_id"] for s in run.steps] == [f"n{i}" for i in range(1, 11)]
    assert all(s["ok"] for s in run.steps)
    assert lab.png(run, 1).startswith(b"\x89PNG")


def test_passwords_and_codes_are_painted_over_in_every_screenshot(lab: Lab) -> None:
    run = lab.run()
    for step in range(1, 11):
        png = lab.png(run, step)
        if step in (1, 2, 3, 4):  # the login page, where the password box is on screen
            assert lab.mask_pixels(png) > 0, f"step {step} shows the password box unmasked"
    # The code box is on screen at steps 5 to 8 and is masked too.
    assert lab.mask_pixels(lab.png(run, 7)) > 0
    # Control: the same kind of screenshot without a mask has none of the mask colour.
    page = lab.browser.new_page()
    try:
        page.goto(f"{lab.mock.base_url}/login")
        assert lab.mask_pixels(page.screenshot()) == 0
    finally:
        page.close()


def test_stopping_at_a_node_returns_a_cleaned_snapshot_of_that_page(lab: Lab) -> None:
    run = lab.run(up_to_node_id="n4")
    assert run.login_result == "stopped_after_node" and run.state == "done"
    html = (lab.folder / "test-runs" / str(run.id) / "snapshot.html").read_text()
    assert 'name="code"' in html  # the code box the owner may want to pick
    assert "<script" not in html and "onclick" not in html
    assert lab.png(run, 1)  # per-step pictures exist as well


def test_an_extract_test_run_reads_the_listing_and_says_which_rule_matched(lab: Lab) -> None:
    url = f"{lab.mock.base_url}/product/1"
    run = lab.run("extract", listing_url=url)
    assert run.state == "done" and run.reading is not None
    assert (run.reading["result"], run.reading["matched_rule"]) == ("in_stock", "in_stock_if")
    lab.mock.control("stock/1", in_stock=False)
    run = lab.run("extract", listing_url=url)
    assert run.reading is not None
    assert (run.reading["result"], run.reading["matched_rule"]) == (
        "out_of_stock", "out_of_stock_if")


def test_a_changed_selector_is_an_unknown_reading_not_a_failed_run(lab: Lab) -> None:
    lab.mock.control("selector", changed=True)
    run = lab.run("extract", listing_url=f"{lab.mock.base_url}/product/1")
    assert run.state == "done" and run.reading is not None
    assert (run.reading["result"], run.reading["error_kind"]) == ("unknown", "flow_failure")
    assert run.snapshot is not None  # so the owner can pick the new element


def test_a_removed_page_is_reported_as_listing_removed(lab: Lab) -> None:
    lab.mock.control("remove/1")
    run = lab.run("extract", listing_url=f"{lab.mock.base_url}/product/1")
    assert run.reading is not None and run.reading["result"] == "listing_removed"


def test_test_runs_leave_stock_data_and_shopify_untouched(lab: Lab) -> None:
    before = lab.table_counts()
    lab.run()
    lab.run("extract", listing_url=f"{lab.mock.base_url}/product/1")
    assert lab.table_counts() == before  # and no_shopify would have failed the run on contact
