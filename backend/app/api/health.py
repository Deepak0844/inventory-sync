"""Health check route used by Docker Compose and the VPS monitor.

Not responsible for deeper checks (worker liveness, Supplier status).
"""

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    """Body of the health check."""

    status: str
    database: str


@router.get("/health")
def health(request: Request, response: Response) -> HealthResponse:
    """Report whether the API can reach the database.

    Returns 200 when the database answers and 503 when it does not.
    """
    if request.app.state.database.ping():
        return HealthResponse(status="ok", database="up")
    response.status_code = 503
    return HealthResponse(status="degraded", database="down")
