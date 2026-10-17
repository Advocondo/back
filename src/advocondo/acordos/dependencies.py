from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from advocondo.acordos.repository import AgreementRepository
from advocondo.acordos.service import AgreementService
from advocondo.condominios.repository import CondominiumRepository
from advocondo.db import get_session
from advocondo.devedores.repository import DebtorRepository


def get_agreement_service(
    session: Annotated[Session, Depends(get_session)],
) -> AgreementService:
    return AgreementService(
        session=session,
        agreements=AgreementRepository(session),
        condominiums=CondominiumRepository(session),
        debtors=DebtorRepository(session),
    )
