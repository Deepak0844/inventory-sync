"""Test run routes for the flow builder. A Test run never writes to Shopify."""

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse, JSONResponse

from app.api.deps import Box, Db, Now, protected
from app.api.schemas import (
    NewTestRun,
    TestRunOut,
    TestRunReadingOut,
    TestRunSnapshotOut,
    TestRunStepOut,
)
from app.db.repos.test_runs import FlowTestRunRecord
from app.services import test_runs as service
from app.services.suppliers import SupplierNotFound

router = APIRouter(**protected(tags=["test-runs"]))

HTML_CSP = "sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src data:"
FILE_TYPES = {".png": "image/png", ".html": "text/html; charset=utf-8"}


@router.post("/test-runs", status_code=status.HTTP_202_ACCEPTED, response_model=None)
def start(body: NewTestRun, session: Db, box: Box, now: Now) -> dict[str, int] | JSONResponse:
    """Queue a Test run and return its id.

    404 for an unknown Supplier. 422 lists every problem with the draft flow, the node,
    the credentials or the Listing URL, and queues nothing. 409 (with `run_id` of the open
    run) when the Supplier already has a Test run in progress, so a new draft is never
    silently answered with an old run.
    """
    try:
        run_id = service.start_test_run(session, box, now, body.supplier_id, body.mode, body.flow,
                                        body.up_to_node_id, body.listing_url)
    except SupplierNotFound:
        raise HTTPException(status_code=404, detail="No such Supplier") from None
    except service.RunRequestInvalid as exc:
        raise HTTPException(status_code=422, detail=exc.messages) from None
    except service.RunInProgress as exc:
        return JSONResponse(status_code=409, content={
            "detail": "A test run is already in progress for this Supplier.",
            "run_id": exc.run_id})
    return {"id": run_id}


@router.get("/test-runs/{run_id}")
def read(run_id: int, session: Db) -> TestRunOut:
    """Return a Test run's state, steps, snapshot and reading."""
    try:
        return _out(service.get_test_run(session, run_id))
    except service.RunNotFound:
        raise HTTPException(status_code=404, detail="No such Test run") from None


@router.get("/test-runs/{run_id}/files/{name}")
def file(run_id: int, name: str, request: Request, session: Db) -> FileResponse:
    """Serve a screenshot or the cleaned snapshot HTML of a run; 404 for any other name.

    The HTML is served sandboxed with a locked-down Content-Security-Policy so the
    page can neither run anything nor load anything, even if the cleaning missed it.
    """
    try:
        path = service.file_path(session, request.app.state.data_dir, run_id, name)
    except service.RunNotFound:
        raise HTTPException(status_code=404, detail="No such file") from None
    headers = {"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"}
    if path.suffix == ".html":
        headers["Content-Security-Policy"] = HTML_CSP
    return FileResponse(path, media_type=FILE_TYPES.get(path.suffix, "application/octet-stream"),
                        headers=headers)


def _out(run: FlowTestRunRecord) -> TestRunOut:
    return TestRunOut(
        id=run.id, state=run.state, mode=run.mode,
        steps=[TestRunStepOut(**s) for s in run.steps],
        snapshot=None if run.snapshot is None else TestRunSnapshotOut(**run.snapshot),
        reading=None if run.reading is None else TestRunReadingOut(**run.reading),
        login_result=run.login_result, error=run.error,
    )
