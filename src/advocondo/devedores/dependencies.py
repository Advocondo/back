from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from advocondo.condominios.repository import CondominiumRepository
from advocondo.db import get_session
from advocondo.devedores.repository import DebtorRepository
from advocondo.devedores.service import DebtorService


def get_debtor_service(
    session: Annotated[Session, Depends(get_session)],
) -> DebtorService:
    return DebtorService(
        session=session,
        debtors=DebtorRepository(session),
        condominiums=CondominiumRepository(session),
    )
