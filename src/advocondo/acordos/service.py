import uuid
from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy.orm import Session

from advocondo.acordos.errors import (
    AgreementNotFoundError,
    DebtorFromAnotherCondominiumError,
    FeeAboveTotalError,
)
from advocondo.acordos.fees import fee_from_percentage
from advocondo.acordos.models import Agreement
from advocondo.acordos.repository import AgreementFilters, AgreementRepository
from advocondo.acordos.schemas import AgreementCreateRequest
from advocondo.condominios.errors import CondominiumNotFoundError
from advocondo.condominios.repository import CondominiumRepository
from advocondo.devedores.errors import DebtorNotFoundError
from advocondo.devedores.repository import DebtorRepository
from advocondo.parcelas.models import Installment
from advocondo.parcelas.plan import monthly_due_dates, split_amount, split_fee
from advocondo.users.models import User


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

    def register(self, request: AgreementCreateRequest, closed_by: User) -> Agreement:
        """Registers an agreement of a debtor with their condominium (US15)."""
        condominium = self._condominiums.get(request.condominium_id)
        if condominium is None:
            raise CondominiumNotFoundError()
        debtor = self._debtors.get(request.debtor_id)
        if debtor is None:
            raise DebtorNotFoundError()
        if debtor.condominium_id != condominium.id:
            raise DebtorFromAnotherCondominiumError()

        fee = fee_in_reais(request)
        agreement = Agreement(
            condominium=condominium,
            debtor=debtor,
            closed_by_id=closed_by.id,
            total_amount=request.total_amount,
            fee_amount=fee,
            fee_percentage=request.fee_percentage,
            installments=build_installments(request, fee),
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


def fee_in_reais(request: AgreementCreateRequest) -> Decimal:
    """The fee typed in reais, or calculated from the percentage (US16-CA01)."""
    if request.fee_amount is not None:
        fee = request.fee_amount
    else:
        assert request.fee_percentage is not None  # ensured by the request schema
        fee = fee_from_percentage(request.total_amount, request.fee_percentage)
    if fee > request.total_amount:
        raise FeeAboveTotalError()
    return fee


def build_installments(
    request: AgreementCreateRequest, fee: Decimal
) -> list[Installment]:
    """Monthly installments that add up to the total amount (US17-CA01, CA02),
    each split between the condominium and the office (US16-CA01, CA02)."""
    amounts = split_amount(request.total_amount, request.installment_count)
    fees = split_fee(amounts, fee)
    due_dates = monthly_due_dates(request.first_due_date, request.installment_count)
    return [
        Installment(
            number=number,
            due_date=due_date,
            amount=amount,
            condominium_amount=amount - installment_fee,
            fee_amount=installment_fee,
        )
        for number, (due_date, amount, installment_fee) in enumerate(
            zip(due_dates, amounts, fees, strict=True), start=1
        )
    ]
