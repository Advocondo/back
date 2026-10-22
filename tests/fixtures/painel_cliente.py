from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Protocol

import pytest
from sqlalchemy.orm import Session

from advocondo.acordos.models import Agreement
from advocondo.condominios.models import Condominium
from advocondo.devedores.models import Debtor
from advocondo.parcelas.models import Installment
from advocondo.users.models import User, UserCondominium

# (due_date, payment_date): one installment each, numbered in the order given.
InstallmentDates = tuple[date, date | None]

INSTALLMENT_AMOUNT = Decimal("100.00")
INSTALLMENT_FEE = Decimal("10.00")


class CreateAgreementWithInstallments(Protocol):
    def __call__(
        self,
        condominium: Condominium,
        debtor: Debtor,
        installments: Sequence[InstallmentDates],
    ) -> Agreement: ...


class LinkClient(Protocol):
    def __call__(self, user: User, *condominiums: Condominium) -> None: ...


@pytest.fixture
def create_agreement_with_installments(
    db_session: Session,
) -> CreateAgreementWithInstallments:
    """Saves an active agreement whose installments have the due and payment dates
    given. There is no way to register a payment yet (US26), so the payment date is
    written straight in the database."""

    def create(
        condominium: Condominium,
        debtor: Debtor,
        installments: Sequence[InstallmentDates],
    ) -> Agreement:
        total = INSTALLMENT_AMOUNT * max(len(installments), 1)
        agreement = Agreement(
            condominium_id=condominium.id,
            debtor_id=debtor.id,
            total_amount=total,
            fee_amount=INSTALLMENT_FEE * max(len(installments), 1),
            fee_percentage=Decimal(10),
        )
        agreement.installments = [
            Installment(
                number=number,
                due_date=due_date,
                payment_date=payment_date,
                amount=INSTALLMENT_AMOUNT,
                condominium_amount=INSTALLMENT_AMOUNT - INSTALLMENT_FEE,
                fee_amount=INSTALLMENT_FEE,
            )
            for number, (due_date, payment_date) in enumerate(installments, start=1)
        ]
        db_session.add(agreement)
        db_session.flush()
        return agreement

    return create


@pytest.fixture
def link_client(db_session: Session) -> LinkClient:
    """Links a Client user to condominiums straight in the database (US10)."""

    def link(user: User, *condominiums: Condominium) -> None:
        db_session.add_all(
            UserCondominium(user_id=user.id, condominium_id=condominium.id)
            for condominium in condominiums
        )
        db_session.flush()

    return link
