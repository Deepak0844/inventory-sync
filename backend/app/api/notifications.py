"""Notification routes, including serving a failure screenshot."""

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import FileResponse

from app.api.deps import Db, Now, protected
from app.api.schemas import NotificationOut
from app.services import workflow

router = APIRouter(**protected(tags=["notifications"]))


@router.get("/notifications")
def notifications(session: Db, resolved: bool = False) -> list[NotificationOut]:
    """List unresolved notifications (or resolved ones with `resolved=true`), newest first."""
    return [
        NotificationOut(
            id=n.id, kind=n.kind, supplier_id=n.supplier_id, supplier_name=n.supplier_name,
            message=n.message, created_at=n.created_at, resolved_at=n.resolved_at,
            screenshot_url=None if n.screenshot_path is None
            else f"/api/notifications/{n.id}/screenshot",
        )
        for n in workflow.list_notifications(session, resolved)
    ]


@router.post("/notifications/{notification_id}/resolve", status_code=status.HTTP_204_NO_CONTENT)
def resolve(notification_id: int, session: Db, now: Now) -> Response:
    """Mark a notification resolved."""
    workflow.resolve_notification(session, now, notification_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/notifications/{notification_id}/screenshot")
def screenshot(notification_id: int, request: Request, session: Db) -> FileResponse:
    """Serve the masked failure screenshot, only from the screenshot folder (404 otherwise)."""
    folder: Path = request.app.state.screenshot_dir
    try:
        return FileResponse(workflow.screenshot_path(session, folder, notification_id))
    except workflow.ScreenshotNotFound:
        raise HTTPException(status_code=404, detail="No screenshot") from None
