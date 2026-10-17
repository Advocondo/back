import uuid
from collections.abc import Sequence

from sqlalchemy.orm import Session

from advocondo.acordos.errors import (
    AgreementNotFoundError,
    DebtorFromAnotherCondominiumError,
)
from advocondo.acordos.models import Agreement
from advocondo.acordos.repository import AgreementFilters, AgreementRepository
from advocondo.acordos.schemas import AgreementCreateRequest
from advocondo.condominios.errors import CondominiumNotFoundError
from advocondo.condominios.repository import CondominiumRepository
from advocondo.devedores.errors import DebtorNotFoundError
from advocondo.devedores.repository import DebtorRepository


class AgreementService:
    def __init__(
        self,
        session: Session,
        agreements: AgreementRepository,
        condominiums: CondominiumRepository,
        debtors: DebtorRepository,
    ) -> None:
        self._session = session
        self._agreements = agreements
        self._condominiums = condominiums
        self._debtors = debtors

    def register(self, request: AgreementCreateRequest) -> Agreement:
        """Registers an agreement of a debtor with their condominium (US15)."""
        condominium = self._condominiums.get(request.condominium_id)
        if condominium is None:
            raise CondominiumNotFoundError()
        debtor = self._debtors.get(request.debtor_id)
        if debtor is None:
            raise DebtorNotFoundError()
        if debtor.condominium_id != condominium.id:
            raise DebtorFromAnotherCondominiumError()

        agreement = Agreement(
            condominium=condominium, debtor=debtor, total_amount=request.total_amount
        )
        self._agreements.save(agreement)
        self._session.commit()
        return agreement

    def get(self, agreement_id: uuid.UUID) -> Agreement:
        agreement = self._agreements.get(agreement_id)
        if agreement is None:
            raise AgreementNotFoundError()
        return agreement

    def search(
        self, filters: AgreementFilters, limit: int, offset: int
    ) -> Sequence[Agreement]:
        return self._agreements.search(filters, limit, offset)
