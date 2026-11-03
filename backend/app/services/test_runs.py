"""Starting and reading Test runs for the flow builder.

Not responsible for running them (the worker's `test_run` job) or for HTTP.
A Test run never writes to Shopify; nothing here can queue anything that does.
"""

from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.encryption import SecretBox
from app.db.repos.jobs import JobRepo
from app.db.repos.suppliers import SupplierRepo
from app.db.repos.test_runs import FlowTestRunRecord, FlowTestRunRepo
from app.flows.definition import FlowDefinition
from app.services.suppliers import SupplierNotFound


class RunRequestInvalid(Exception):
    """The Test run cannot start. `messages` say why, for the builder."""

    def __init__(self, messages: list[str]) -> None:
        super().__init__("; ".join(messages))
        self.messages = messages


class RunInProgress(Exception):
    """The Supplier already has a Test run in progress. `run_id` is that run."""

    def __init__(self, run_id: int) -> None:
        super().__init__(f"test run {run_id} is already in progress")
        self.run_id = run_id


class RunNotFound(Exception):
    """No such Test run, or no such file in it."""


def start_test_run(
    session: Session, box: SecretBox, now: datetime, supplier_id: int, mode: str,
    flow: dict[str, Any] | None, up_to_node_id: str | None, listing_url: str | None,
) -> int:
    """Queue a Test run and return its id.

    Args:
        supplier_id: The Supplier to test.
        mode: "login" or "extract".
        flow: An unsaved draft to run, or None for the saved flow.
        up_to_node_id: Stop after this node and snapshot the page there.
        listing_url: The page to read in "extract" mode.

    Raises:
        SupplierNotFound: for an unknown id.
        RunRequestInvalid: for a bad draft, an unknown node, no flow, no credentials, or no
            Listing URL in extract mode. Nothing is queued. Checked before anything else, so a
            bad request is never answered with "already in progress".
        RunInProgress: if the Supplier has a run that is still open (and under 30 minutes
            old). The new request is not queued; the owner must wait or let it finish.
    """
    suppliers = SupplierRepo(session, box)
    if suppliers.get(supplier_id) is None:
        raise SupplierNotFound(supplier_id)
    runs = FlowTestRunRepo(session)
    problems: list[str] = []
    if mode == "extract" and not listing_url:
        problems.append("Give a Listing URL to test the extract step.")
    raw = flow if flow is not None else suppliers.get_flow(supplier_id)
    if raw is None:
        problems.append("This Supplier has no flow yet. Save one or send a draft.")
    else:
        parsed, found = _parse_draft(raw, up_to_node_id)
        problems += found
        if parsed is not None:
            # A snapshot of the login page needs no password, and the owner needs that snapshot
            # to pick the selectors in the first place, so only demand what will really run.
            if (mode == "extract" or parsed.uses_credentials(up_to_node_id)) and (
                suppliers.get_credentials(supplier_id) is None
            ):
                problems.append("Add the Supplier's credentials before a Test run.")
            if mode == "extract" and not parsed.extract.stock_selector:
                problems.append("Choose the Stock element first (under Stock rules).")
    if problems:
        raise RunRequestInvalid(problems)
    open_run = runs.open_for_supplier(supplier_id, now)
    if open_run is not None:
        raise RunInProgress(open_run.id)
    request = {"supplier_id": supplier_id, "mode": mode, "flow": flow,
               "up_to_node_id": up_to_node_id, "listing_url": listing_url}
    run_id = runs.create(supplier_id, mode, request, now)
    JobRepo(session).enqueue("test_run", supplier_id, {"test_run_id": run_id}, run_after=now,
                             now=now)
    return run_id


def _parse_draft(
    raw: dict[str, Any], up_to_node_id: str | None
) -> tuple[FlowDefinition | None, list[str]]:
    """Validate a draft as a Test run accepts it: structure must be right, but the stock
    selector may still be empty. Returns the flow (None if invalid) and the problems."""
    try:
        flow = FlowDefinition.model_validate(raw, context={"draft": True})
    except ValidationError as exc:
        return None, [f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}".lstrip(": ")
                      for e in exc.errors()]
    if up_to_node_id is not None and up_to_node_id not in {n.id for n in flow.nodes}:
        return None, [f"The flow has no node {up_to_node_id!r}."]
    return flow, []


def get_test_run(session: Session, run_id: int) -> FlowTestRunRecord:
    """Return a Test run. Raises RunNotFound."""
    run = FlowTestRunRepo(session).get(run_id)
    if run is None:
        raise RunNotFound(run_id)
    return run


def recorded_files(run: FlowTestRunRecord) -> set[str]:
    """The file names this run recorded (its step screenshots and its snapshot)."""
    urls = [s.get("screenshot_url") for s in run.steps]
    if run.snapshot:
        urls += [run.snapshot.get("screenshot_url"), run.snapshot.get("html_url")]
    return {u.rsplit("/", 1)[-1] for u in urls if isinstance(u, str)}


def file_path(session: Session, data_dir: Path, run_id: int, name: str) -> Path:
    """Return the path of one recorded file of a run.

    Only names the run itself recorded are served, so a request can never name
    another path. Raises RunNotFound for an unknown run, an unrecorded name, or a
    file that is gone.
    """
    run = get_test_run(session, run_id)
    if name not in recorded_files(run):  # first, so odd bytes never reach the filesystem
        raise RunNotFound(name)
    folder = (data_dir / "test-runs" / str(run_id)).resolve()
    path = (folder / name).resolve()
    if path.parent != folder or not path.is_file():
        raise RunNotFound(name)
    return path
