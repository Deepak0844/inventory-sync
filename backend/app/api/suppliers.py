"""Supplier routes: CRUD, write-only credentials, the flow, and worker actions."""

from typing import Any

from fastapi import APIRouter, HTTPException, Response, status

from app.api.deps import Box, Db, Now, protected
from app.api.schemas import (
    CredentialsIn,
    CredentialsOut,
    FlowJson,
    RunsOut,
    SupplierCreate,
    SupplierOut,
    SupplierPatch,
)
from app.services import suppliers as service

router = APIRouter(**protected(tags=["suppliers"]))
NOT_FOUND = HTTPException(status_code=404, detail="Supplier not found")


@router.get("/suppliers")
def list_suppliers(session: Db, box: Box, now: Now) -> list[SupplierOut]:
    """List every Supplier with its derived health."""
    return [SupplierOut.model_validate(s) for s in service.list_suppliers(session, box, now)]


@router.post("/suppliers", status_code=status.HTTP_201_CREATED)
def create_supplier(body: SupplierCreate, session: Db, box: Box, now: Now) -> SupplierOut:
    """Add a Supplier. 409 if the name is taken."""
    try:
        view = service.create_supplier(session, box, now, **body.model_dump())
    except service.DuplicateSupplier:
        raise HTTPException(status_code=409, detail="A Supplier with that name exists") from None
    return SupplierOut.model_validate(view)


@router.get("/suppliers/{supplier_id}")
def get_supplier(supplier_id: int, session: Db, box: Box, now: Now) -> SupplierOut:
    """Return one Supplier (404 if unknown)."""
    try:
        return SupplierOut.model_validate(service.get_supplier(session, box, now, supplier_id))
    except service.SupplierNotFound:
        raise NOT_FOUND from None


@router.patch("/suppliers/{supplier_id}")
def patch_supplier(
    supplier_id: int, body: SupplierPatch, session: Db, box: Box, now: Now
) -> SupplierOut:
    """Change the given fields (404 if unknown, 409 on a name clash)."""
    try:
        view = service.update_supplier(
            session, box, now, supplier_id, **body.model_dump(exclude_unset=True)
        )
    except service.SupplierNotFound:
        raise NOT_FOUND from None
    except service.DuplicateSupplier:
        raise HTTPException(status_code=409, detail="A Supplier with that name exists") from None
    return SupplierOut.model_validate(view)


@router.delete("/suppliers/{supplier_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_supplier(supplier_id: int, session: Db, box: Box) -> Response:
    """Delete a Supplier and everything under it (404 if unknown)."""
    try:
        service.delete_supplier(session, box, supplier_id)
    except service.SupplierNotFound:
        raise NOT_FOUND from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/suppliers/{supplier_id}/credentials", status_code=status.HTTP_204_NO_CONTENT)
def put_credentials(supplier_id: int, body: CredentialsIn, session: Db, box: Box) -> Response:
    """Store the Supplier login, encrypted. The password is never returned."""
    try:
        service.set_credentials(session, box, supplier_id, body.username, body.password)
    except service.SupplierNotFound:
        raise NOT_FOUND from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/suppliers/{supplier_id}/credentials")
def get_credentials(supplier_id: int, session: Db, box: Box) -> CredentialsOut:
    """Return the username and whether a password is set."""
    try:
        username, has_password = service.credentials_status(session, box, supplier_id)
    except service.SupplierNotFound:
        raise NOT_FOUND from None
    return CredentialsOut(username=username, has_password=has_password)


@router.get("/suppliers/{supplier_id}/flow")
def get_flow(supplier_id: int, session: Db, box: Box) -> FlowJson:
    """Return the flow JSON (404 if the Supplier or its flow does not exist)."""
    try:
        flow = service.get_flow(session, box, supplier_id)
    except service.SupplierNotFound:
        raise NOT_FOUND from None
    if flow is None:
        raise HTTPException(status_code=404, detail="No flow yet")
    return flow


@router.put("/suppliers/{supplier_id}/flow")
def put_flow(supplier_id: int, body: dict[str, Any], session: Db, box: Box) -> FlowJson:
    """Validate and store the flow. 422 lists every problem and saves nothing."""
    try:
        return service.save_flow(session, box, supplier_id, body)
    except service.SupplierNotFound:
        raise NOT_FOUND from None
    except service.FlowInvalid as exc:
        raise HTTPException(status_code=422, detail=exc.messages) from None


def _queue(kind: str, supplier_id: int, session: Db, box: Box, now: Now) -> Response:
    try:
        service.queue_action(session, box, now, supplier_id, kind)
    except service.SupplierNotFound:
        raise NOT_FOUND from None
    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.post("/suppliers/{supplier_id}/login", status_code=status.HTTP_202_ACCEPTED)
def login_now(supplier_id: int, session: Db, box: Box, now: Now) -> Response:
    """The Login button: queue a login run for the worker."""
    return _queue("login", supplier_id, session, box, now)


@router.post("/suppliers/{supplier_id}/check", status_code=status.HTTP_202_ACCEPTED)
def check_now(supplier_id: int, session: Db, box: Box, now: Now) -> Response:
    """Queue a check of this Supplier's Listings now."""
    return _queue("check_supplier", supplier_id, session, box, now)


@router.post("/suppliers/{supplier_id}/retry", status_code=status.HTTP_202_ACCEPTED)
def retry(supplier_id: int, session: Db, box: Box, now: Now) -> Response:
    """Clear a pause and queue a check."""
    try:
        service.retry_supplier(session, box, now, supplier_id)
    except service.SupplierNotFound:
        raise NOT_FOUND from None
    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.get("/suppliers/{supplier_id}/runs")
def runs(supplier_id: int, session: Db, box: Box) -> RunsOut:
    """List the Supplier's runs, newest first."""
    try:
        records = service.list_runs(session, box, supplier_id)
    except service.SupplierNotFound:
        raise NOT_FOUND from None
    return RunsOut.model_validate({"items": records})
