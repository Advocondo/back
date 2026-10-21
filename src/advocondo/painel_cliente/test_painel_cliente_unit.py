import uuid
from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from advocondo.acordos.models import Agreement
from advocondo.condominios.models import Condominium
from advocondo.devedores.models import Debtor
from advocondo.painel_cliente.repository import (
    ClientPanelRepository,
    client_agreements_query,
)
from advocondo.painel_cliente.schemas import AgreementStanding
from advocondo.painel_cliente.service import ClientPanelService, summarize_agreement
from advocondo.parcelas.models import Installment

TODAY = date(2026, 3, 10)
PAID_ON = date(2026, 2, 1)


def make_agreement(
    installments: Sequence[tuple[date, date | None]],
    condominium_name: str = "Mirante",
    debtor_name: str = "José",
) -> Agreement:
    agreement = Agreement(
        id=uuid.uuid4(),
        condominium=Condominium(name=condominium_name),
        debtor=Debtor(name=debtor_name, unit="Bloco B 304"),
    )
    agreement.installments = [
        Installment(
            number=number,
            due_date=due_date,
            payment_date=payment_date,
            amount=Decimal("100.00"),
        )
        for number, (due_date, payment_date) in enumerate(installments, start=1)
    ]
    return agreement


class FakeRepository(ClientPanelRepository):
    def __init__(self, agreements: list[Agreement]) -> None:
        self._agreements = agreements

    def list_agreements_of_client(self, user_id: uuid.UUID) -> list[Agreement]:
        return self._agreements


class TestSummarizeAgreement:
    def test_agreement_without_installments_is_on_time(self) -> None:
        summary = summarize_agreement(make_agreement([]), TODAY)

        assert summary.status == AgreementStanding.ON_TIME
        assert summary.overdue_installments == 0
        assert summary.next_due_date is None

    def test_agreement_with_everything_paid_is_on_time(self) -> None:
        agreement = make_agreement(
            [(date(2026, 2, 10), PAID_ON), (date(2026, 3, 10), PAID_ON)]
        )

        summary = summarize_agreement(agreement, TODAY)

        assert summary.status == AgreementStanding.ON_TIME
        assert summary.next_due_date is None

    def test_one_overdue_installment_makes_the_agreement_overdue(self) -> None:
        agreement = make_agreement(
            [(date(2026, 2, 10), PAID_ON), (date(2026, 3, 9), None)]
        )

        summary = summarize_agreement(agreement, TODAY)

        assert summary.status == AgreementStanding.OVERDUE
        assert summary.overdue_installments == 1

    def test_installment_due_today_is_not_overdue(self) -> None:
        summary = summarize_agreement(make_agreement([(TODAY, None)]), TODAY)

        assert summary.status == AgreementStanding.ON_TIME
        assert summary.next_due_date == TODAY

    def test_overdue_installments_are_counted(self) -> None:
        agreement = make_agreement(
            [(date(2026, 1, 10), None), (date(2026, 2, 10), None), (TODAY, None)]
        )

        assert summarize_agreement(agreement, TODAY).overdue_installments == 2

    def test_next_due_date_is_the_earliest_unpaid_installment_not_overdue(
        self,
    ) -> None:
        agreement = make_agreement(
            [
                (date(2026, 2, 10), None),
                (date(2026, 4, 10), None),
                (date(2026, 3, 20), None),
                (date(2026, 3, 15), PAID_ON),
            ]
        )

        assert summarize_agreement(agreement, TODAY).next_due_date == date(2026, 3, 20)

    def test_summary_names_the_condominium_and_the_debtor(self) -> None:
        summary = summarize_agreement(make_agreement([]), TODAY)

        assert summary.condominium_name == "Mirante"
        assert summary.debtor_name == "José"
        assert summary.debtor_unit == "Bloco B 304"


class TestListAgreements:
    def test_overdue_first_then_condominium_then_debtor(self) -> None:
        on_time = [(date(2026, 4, 10), None)]
        overdue = [(date(2026, 3, 1), None)]
        agreements = [
            make_agreement(on_time, "Aurora", "Ana"),
            make_agreement(overdue, "Zênite", "Zé"),
            make_agreement(on_time, "Aurora", "Bia"),
            make_agreement(overdue, "Mirante", "Caio"),
            make_agreement(overdue, "Mirante", "Beto"),
        ]
        service = ClientPanelService(FakeRepository(agreements))

        result = service.list_agreements(uuid.uuid4(), TODAY)

        assert [(item.condominium_name, item.debtor_name) for item in result] == [
            ("Mirante", "Beto"),
            ("Mirante", "Caio"),
            ("Zênite", "Zé"),
            ("Aurora", "Ana"),
            ("Aurora", "Bia"),
        ]


def test_query_filters_active_agreements_only() -> None:
    """The status column accepts only 'active' (CHECK), so no other agreement can be
    saved to test with data. Swap this for an integration test when a second status
    exists."""
    sql = str(
        client_agreements_query(uuid.uuid4()).compile(
            compile_kwargs={"literal_binds": True}
        )
    )

    assert "agreements.status = 'active'" in sql
