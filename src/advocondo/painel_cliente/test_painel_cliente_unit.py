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
from advocondo.painel_cliente.schemas import AgreementStanding, MonthStanding
from advocondo.painel_cliente.service import (
    ClientPanelService,
    summarize_agreement,
    summarize_months,
)
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
        debtor=Debtor(id=uuid.uuid4(), name=debtor_name, unit="Bloco B 304"),
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


def make_installment(
    due_date: date, paid: str = "0.00", payment_date: date | None = None
) -> Installment:
    """R$ 100,00 installment with `paid` already received."""
    return Installment(
        due_date=due_date,
        amount=Decimal("100.00"),
        paid_amount=Decimal(paid),
        payment_date=payment_date,
    )


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
    def test_overdue_first_keeping_the_repository_order(self) -> None:
        on_time = [(date(2026, 4, 10), None)]
        overdue = [(date(2026, 3, 1), None)]
        agreements = [
            make_agreement(on_time, "Aurora", "Ana"),
            make_agreement(overdue, "Mirante", "Beto"),
            make_agreement(on_time, "Mirante", "Bia"),
            make_agreement(overdue, "Zênite", "Zé"),
        ]
        service = ClientPanelService(FakeRepository(agreements))

        result = service.list_agreements(uuid.uuid4(), TODAY)

        assert [(item.condominium_name, item.debtor_name) for item in result] == [
            ("Mirante", "Beto"),
            ("Zênite", "Zé"),
            ("Aurora", "Ana"),
            ("Mirante", "Bia"),
        ]


class TestSummarizeMonths:
    """US38. Hoje é 10 de março de 2026."""

    def test_fully_paid_month(self) -> None:
        months = summarize_months(
            [make_installment(date(2026, 2, 10), "100.00", PAID_ON)], [], TODAY
        )

        assert [(m.month, m.paid_amount, m.open_amount, m.status) for m in months] == [
            ("2026-02", Decimal("100.00"), Decimal("0.00"), MonthStanding.PAID)
        ]

    def test_partly_paid_overdue_month(self) -> None:
        """US28: o pagamento parcial entra no pago e o resto no em aberto."""
        months = summarize_months(
            [make_installment(date(2026, 3, 9), "40.00")], [], TODAY
        )

        assert months[0].paid_amount == Decimal("40.00")
        assert months[0].open_amount == Decimal("60.00")
        assert months[0].status == MonthStanding.OVERDUE

    def test_future_month_is_open(self) -> None:
        months = summarize_months([make_installment(date(2026, 4, 10))], [], TODAY)

        assert months[0].status == MonthStanding.OPEN
        assert months[0].open_amount == Decimal("100.00")

    def test_installments_of_the_same_month_add_up(self) -> None:
        """Dois acordos do morador com vencimento no mesmo mês."""
        months = summarize_months(
            [
                make_installment(date(2026, 2, 5), "100.00", PAID_ON),
                make_installment(date(2026, 2, 20)),
            ],
            [],
            TODAY,
        )

        assert len(months) == 1
        assert months[0].paid_amount == Decimal("100.00")
        assert months[0].open_amount == Decimal("100.00")
        assert months[0].status == MonthStanding.OVERDUE

    def test_overdue_wins_over_open_in_the_same_month(self) -> None:
        months = summarize_months(
            [make_installment(date(2026, 3, 9)), make_installment(date(2026, 3, 31))],
            [],
            TODAY,
        )

        assert months[0].status == MonthStanding.OVERDUE

    def test_months_come_oldest_first(self) -> None:
        months = summarize_months(
            [
                make_installment(date(2026, 4, 10)),
                make_installment(date(2025, 12, 10)),
                make_installment(date(2026, 1, 10)),
            ],
            [],
            TODAY,
        )

        assert [m.month for m in months] == ["2025-12", "2026-01", "2026-04"]

    def test_cancelled_agreements_only_add_what_was_paid(self) -> None:
        """O que não foi pago no acordo cancelado saiu da cobrança (US20)."""
        months = summarize_months(
            [],
            [
                make_installment(date(2026, 1, 10), "100.00", PAID_ON),
                make_installment(date(2026, 2, 10), "30.00"),
                make_installment(date(2026, 3, 9)),
            ],
            TODAY,
        )

        assert [(m.month, m.paid_amount, m.open_amount, m.status) for m in months] == [
            ("2026-01", Decimal("100.00"), Decimal(0), MonthStanding.PAID),
            ("2026-02", Decimal("30.00"), Decimal(0), MonthStanding.PAID),
        ]

    def test_cancelled_payment_joins_a_month_still_being_charged(self) -> None:
        months = summarize_months(
            [make_installment(date(2026, 2, 20))],
            [make_installment(date(2026, 2, 10), "100.00", PAID_ON)],
            TODAY,
        )

        assert months[0].paid_amount == Decimal("100.00")
        assert months[0].open_amount == Decimal("100.00")
        assert months[0].status == MonthStanding.OVERDUE

    def test_no_installments_no_months(self) -> None:
        assert summarize_months([], [], TODAY) == []


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
