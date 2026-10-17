from datetime import date

from sqlalchemy.orm import Session

from advocondo.condominios.errors import (
    CnpjAlreadyRegisteredError,
    InvalidContractDatesError,
)
from advocondo.condominios.models import Condominium
from advocondo.condominios.repository import CondominiumRepository
from advocondo.condominios.schemas import CondominiumCreateRequest


class CondominiumService:
    def __init__(self, session: Session, condominiums: CondominiumRepository) -> None:
        self._session = session
        self._condominiums = condominiums

    def register(self, request: CondominiumCreateRequest) -> Condominium:
        """Registers a condominium so agreements and Client users can be linked to it."""
        self._ensure_cnpj_is_free(request.cnpj)
        ensure_contract_dates_are_consistent(
            request.contract_start_date, request.contract_renewal_date
        )
        condominium = Condominium(**request.model_dump())
        self._condominiums.add(condominium)
        self._session.commit()
        return condominium

    def _ensure_cnpj_is_free(
        self, cnpj: str | None, condominium_being_edited: Condominium | None = None
    ) -> None:
        if cnpj is None:
            return
        owner = self._condominiums.get_by_cnpj(cnpj)
        if owner is not None and owner is not condominium_being_edited:
            raise CnpjAlreadyRegisteredError()


def ensure_contract_dates_are_consistent(
    start_date: date | None, renewal_date: date | None
) -> None:
    if start_date and renewal_date and renewal_date < start_date:
        raise InvalidContractDatesError()
