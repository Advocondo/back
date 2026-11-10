import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from advocondo.auditoria.dependencies import get_audit_trail_service
from advocondo.auditoria.repository import AuditCategory
from advocondo.auditoria.schemas import AuditEntryResponse, AuditTrailResponse
from advocondo.auditoria.service import AuditTrailService
from advocondo.users.dependencies import CurrentAdmin

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("")
def list_audit_trail(
    current_admin: CurrentAdmin,
    service: Annotated[AuditTrailService, Depends(get_audit_trail_service)],
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    offset: Annotated[int, Query(ge=0)] = 0,
    actor_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    category: AuditCategory | None = None,
) -> AuditTrailResponse:
    page = service.list(
        limit=limit,
        offset=offset,
        actor_id=actor_id,
        date_from=date_from,
        date_to=date_to,
        category=category,
    )
    return AuditTrailResponse(
        total=page.total,
        entries=[AuditEntryResponse.model_validate(entry) for entry in page.entries],
    )
