from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from advocondo.condominios.repository import CondominiumRepository
from advocondo.condominios.service import CondominiumService
from advocondo.db import get_session


def get_condominium_service(
    session: Annotated[Session, Depends(get_session)],
) -> CondominiumService:
    return CondominiumService(session, CondominiumRepository(session))
