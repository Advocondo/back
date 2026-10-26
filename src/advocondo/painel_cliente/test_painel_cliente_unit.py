import uuid
from collections.abc import Sequence
from datetime import date
from decimal import Decimal

import pytest

from advocondo.acordos.models import Agreement
from advocondo.condominios.models import Condominium
from advocondo.devedores.models import Debtor
from advocondo.painel_cliente.report_pdf import render_condominium_report
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
from tests.support.pdf import pdf_text

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
    @pytest.mark.parametrize(
        ("installments", "status", "overdue", "next_due_date"),
        [
            pytest.param([], AgreementStanding.ON_TIME, 0, None, id="no-installments"),
            pytest.param(
                [(date(2026, 2, 10), PAID_ON), (date(2026, 3, 10), PAID_ON)],
                AgreementStanding.ON_TIME,
                0,
                None,
                id="everything-paid",
            ),
            pytest.param(
                [(date(2026, 2, 10), PAID_ON), (date(2026, 3, 9), None)],
                AgreementStanding.OVERDUE,
                1,
                None,
                id="one-overdue",
            ),
            pytest.param(
                [(TODAY, None)],
                AgreementStanding.ON_TIME,
                0,
                TODAY,
                id="due-today-is-not-overdue",
            ),
            pytest.param(
                [(date(2026, 1, 10), None), (date(2026, 2, 10), None), (TODAY, None)],
                AgreementStanding.OVERDUE,
                2,
                TODAY,
                id="overdue-are-counted",
            ),
            pytest.param(
                [
                    (date(2026, 2, 10), None),
                    (date(2026, 4, 10), None),
                    (date(2026, 3, 20), None),
                    (date(2026, 3, 15), PAID_ON),
                ],
                AgreementStanding.OVERDUE,
                1,
                date(2026, 3, 20),
                id="next-due-is-the-earliest-unpaid-not-overdue",
            ),
        ],
    )
    def test_status_overdue_count_and_next_due_date(
        self,
        installments: list[tuple[date, date | None]],
        status: AgreementStanding,
        overdue: int,
        next_due_date: date | None,
    ) -> None:
        """US37-CA02: hoje é 10/03; a parcela vence no fim do dia."""
        summary = summarize_agreement(make_agreement(installments), TODAY)

        assert summary.status == status
        assert summary.overdue_installments == overdue
        assert summary.next_due_date == next_due_date

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


MonthRow = tuple[str, str, str, MonthStanding]


class TestSummarizeMonths:
    """US38. Hoje é 10 de março de 2026."""

    @pytest.mark.parametrize(
        ("collected", "cancelled", "expected"),
        [
            pytest.param([], [], [], id="no-installments"),
            pytest.param(
                [make_installment(date(2026, 2, 10), "100.00", PAID_ON)],
                [],
                [("2026-02", "100.00", "0.00", MonthStanding.PAID)],
                id="fully-paid",
            ),
            pytest.param(
                [make_installment(date(2026, 3, 9), "40.00")],
                [],
                [("2026-03", "40.00", "60.00", MonthStanding.OVERDUE)],
                id="us28-partly-paid-and-overdue",
            ),
            pytest.param(
                [make_installment(date(2026, 4, 10))],
                [],
                [("2026-04", "0.00", "100.00", MonthStanding.OPEN)],
                id="future-month-is-open",
            ),
            pytest.param(
                [
                    make_installment(date(2026, 2, 5), "100.00", PAID_ON),
                    make_installment(date(2026, 2, 20)),
                ],
                [],
                [("2026-02", "100.00", "100.00", MonthStanding.OVERDUE)],
                id="two-agreements-in-the-same-month-add-up",
            ),
            pytest.param(
                [
                    make_installment(date(2026, 3, 9)),
                    make_installment(date(2026, 3, 31)),
                ],
                [],
                [("2026-03", "0.00", "200.00", MonthStanding.OVERDUE)],
                id="overdue-wins-over-open",
            ),
            pytest.param(
                [
                    make_installment(date(2026, 4, 10)),
                    make_installment(date(2025, 12, 10)),
                    make_installment(date(2026, 1, 10)),
                ],
                [],
                [
                    ("2025-12", "0.00", "100.00", MonthStanding.OVERDUE),
                    ("2026-01", "0.00", "100.00", MonthStanding.OVERDUE),
                    ("2026-04", "0.00", "100.00", MonthStanding.OPEN),
                ],
                id="oldest-month-first",
            ),
            pytest.param(
                [],
                [
                    make_installment(date(2026, 1, 10), "100.00", PAID_ON),
                    make_installment(date(2026, 2, 10), "30.00"),
                    make_installment(date(2026, 3, 9)),
                ],
                [
                    ("2026-01", "100.00", "0.00", MonthStanding.PAID),
                    ("2026-02", "30.00", "0.00", MonthStanding.PAID),
                ],
                id="us20-cancelled-adds-only-what-was-paid",
            ),
            pytest.param(
                [make_installment(date(2026, 2, 20))],
                [make_installment(date(2026, 2, 10), "100.00", PAID_ON)],
                [("2026-02", "100.00", "100.00", MonthStanding.OVERDUE)],
                id="cancelled-payment-joins-a-month-still-charged",
            ),
        ],
    )
    def test_months_add_what_was_paid_and_what_is_open(
        self,
        collected: list[Installment],
        cancelled: list[Installment],
        expected: list[MonthRow],
    ) -> None:
        """US38-CA01"""
        months = summarize_months(collected, cancelled, TODAY)

        assert [
            (m.month, f"{m.paid_amount:.2f}", f"{m.open_amount:.2f}", m.status)
            for m in months
        ] == expected


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


class TestCondominiumReport:
    """US39-CA02: o relatório só mostra dados do condomínio do Cliente."""

    @pytest.mark.parametrize(
        ("cnpj", "shown", "hidden"),
        [
            pytest.param("11222333000181", "11222333000181", None, id="with-cnpj"),
            pytest.param(None, "Residencial Mirante", "CNPJ", id="without-cnpj"),
        ],
    )
    def test_condominium_data_in_the_report(
        self, cnpj: str | None, shown: str, hidden: str | None
    ) -> None:
        condominium = Condominium(name="Residencial Mirante", cnpj=cnpj)

        text = pdf_text(
            render_condominium_report("Síndico", condominium, [], date(2026, 3, 2))
        )

        assert shown in text
        if hidden is not None:
            assert hidden not in text
