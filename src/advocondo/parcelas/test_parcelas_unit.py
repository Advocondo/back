from datetime import date, timedelta

import pytest

from advocondo.parcelas.status import ParcelaStatus, calculate_parcela_status

TODAY = date(2026, 10, 15)


class TestCalculateParcelaStatus:
    @pytest.mark.parametrize(
        ("days_until_due", "expected"),
        [
            pytest.param(5, ParcelaStatus.EM_ABERTO, id="due-in-a-few-days"),
            pytest.param(0, ParcelaStatus.EM_ABERTO, id="due-today-not-overdue-yet"),
            pytest.param(-1, ParcelaStatus.ATRASADO, id="due-yesterday"),
            pytest.param(-300, ParcelaStatus.ATRASADO, id="due-long-ago"),
        ],
    )
    def test_unpaid_parcela_is_overdue_only_after_the_due_date(
        self, days_until_due: int, expected: ParcelaStatus
    ) -> None:
        """US27-CA01"""
        due_date = TODAY + timedelta(days=days_until_due)

        status = calculate_parcela_status(due_date, payment_date=None, today=TODAY)

        assert status == expected

    @pytest.mark.parametrize(
        ("days_until_due", "days_until_payment"),
        [
            pytest.param(5, -5, id="paid-before-the-due-date"),
            pytest.param(0, 0, id="paid-on-the-due-date"),
            pytest.param(-35, -14, id="paid-late-stays-paid"),
        ],
    )
    def test_paid_parcela_is_never_overdue(
        self, days_until_due: int, days_until_payment: int
    ) -> None:
        """US27-CA01"""
        due_date = TODAY + timedelta(days=days_until_due)
        payment_date = TODAY + timedelta(days=days_until_payment)

        status = calculate_parcela_status(due_date, payment_date, today=TODAY)

        assert status == ParcelaStatus.PAGO