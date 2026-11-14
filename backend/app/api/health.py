from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Response
from pydantic import BaseModel

from .. import __version__
from ..config import get_settings
from ..db import check_database

router = APIRouter(tags=["system"])


class ComponentStatus(BaseModel):
    status: Literal["ok", "error"]
    error: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    environment: str
    time_utc: datetime
    components: dict[str, ComponentStatus]


@router.get("/health", response_model=HealthResponse, summary="Service health")
def health(response: Response) -> HealthResponse:
    """Liveness plus a database connectivity check. Returns 503 when a dependency is down."""
    db_ok, db_err = check_database()
    if not db_ok:
        response.status_code = 503
    return HealthResponse(
        status="ok" if db_ok else "degraded",
        version=__version__,
        environment=get_settings().env,
        time_utc=datetime.now(timezone.utc),
        components={"database": ComponentStatus(status="ok" if db_ok else "error", error=db_err)},
    )
