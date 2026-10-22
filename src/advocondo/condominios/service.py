import uuid
from collections.abc import Sequence
from datetime import date

from sqlalchemy.orm import Session

from advocondo.condominios.errors import (
    CnpjAlreadyRegisteredError,
    CondominiumNotFoundError,
    InvalidContractDatesError,
)
from advocondo.condominios.models import Condominium
from advocondo.condominios.repository import CondominiumRepository
from advocondo.condominios.schemas import (
    CondominiumCreateRequest,
    CondominiumUpdateRequest,
)


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
        self._condominiums.save(condominium)
        self._session.commit()
        return condominium

    def update(
        self, condominium_id: uuid.UUID, request: CondominiumUpdateRequest
    ) -> Condominium:
        """Edits a registered condominium, e.g. when the management company changes."""
        condominium = self.get(condominium_id)
        changes = request.model_dump(exclude_unset=True)
        if "cnpj" in changes:
            self._ensure_cnpj_is_free(changes["cnpj"], condominium)
        # Checked against the final state: a request may send only one of the dates.
        ensure_contract_dates_are_consistent(
            changes.get("contract_start_date", condominium.contract_start_date),
            changes.get("contract_renewal_date", condominium.contract_renewal_date),
        )
        for field_name, new_value in changes.items():
            setattr(condominium, field_name, new_value)
        self._condominiums.save(condominium)
        self._session.commit()
        return condominium

    def get(self, condominium_id: uuid.UUID) -> Condominium:
        condominium = self._condominiums.get(condominium_id)
        if condominium is None:
            raise CondominiumNotFoundError()
        return condominium

    def search(
        self, text: str | None, limit: int, offset: int
    ) -> Sequence[Condominium]:
        search_text = text.strip() if text else None
        return self._condominiums.search(search_text or None, limit, offset)

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
