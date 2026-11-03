"""Pending Approval routes."""

from fastapi import APIRouter, HTTPException, Response, status

from app.api.deps import Db, Now, protected
from app.api.schemas import ApprovalOut
from app.services import workflow

router = APIRouter(**protected(tags=["approvals"]))
GONE = HTTPException(status_code=404, detail="Nothing is waiting for approval with that id")


@router.get("/approvals")
def approvals(session: Db) -> list[ApprovalOut]:
    """List held change batches waiting for the owner."""
    return [ApprovalOut.model_validate(a) for a in workflow.list_approvals(session)]


@router.post("/approvals/{approval_id}/approve", status_code=status.HTTP_202_ACCEPTED)
def approve(approval_id: int, session: Db, now: Now) -> Response:
    """Approve a batch; the worker applies it to Shopify. 404 if unknown or already decided."""
    try:
        workflow.approve(session, now, approval_id)
    except workflow.ApprovalNotFound:
        raise GONE from None
    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.post("/approvals/{approval_id}/reject", status_code=status.HTTP_204_NO_CONTENT)
def reject(approval_id: int, session: Db, now: Now) -> Response:
    """Discard a batch. 404 if unknown or already decided."""
    try:
        workflow.reject(session, now, approval_id)
    except workflow.ApprovalNotFound:
        raise GONE from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
