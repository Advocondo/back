from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from advocondo.auditoria.repository import AuditTrailRepository
from advocondo.auditoria.service import AuditTrailService
from advocondo.db import get_session


def get_audit_trail_service(
    session: Annotated[Session, Depends(get_session)],
) -> AuditTrailService:
    return AuditTrailService(AuditTrailRepository(session))
