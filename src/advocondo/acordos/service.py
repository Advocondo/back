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
from advocondo.parcelas.models import Installment
from advocondo.parcelas.plan import monthly_due_dates, split_amount


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
            condominium=condominium,
            debtor=debtor,
            total_amount=request.total_amount,
            installments=build_installments(request),
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


def build_installments(request: AgreementCreateRequest) -> list[Installment]:
    """Monthly installments that add up to the total amount (US17-CA01, CA02)."""
    amounts = split_amount(request.total_amount, request.installment_count)
    due_dates = monthly_due_dates(request.first_due_date, request.installment_count)
    return [
        Installment(number=number, due_date=due_date, amount=amount)
        for number, (due_date, amount) in enumerate(
            zip(due_dates, amounts, strict=True), start=1
        )
    ]
