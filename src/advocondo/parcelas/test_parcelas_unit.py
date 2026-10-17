from datetime import date
from decimal import Decimal

import pytest

from advocondo.parcelas.errors import InstallmentBelowOneCentError
from advocondo.parcelas.plan import monthly_due_dates, split_amount


class TestSplitAmount:
    @pytest.mark.parametrize(
        ("total", "count", "expected"),
        [
            pytest.param("5500.00", 10, ["550.00"] * 10, id="divides-evenly"),
            pytest.param("100.00", 3, ["33.33", "33.33", "33.34"], id="cents-to-last"),
            pytest.param("0.05", 5, ["0.01"] * 5, id="one-cent-each"),
            pytest.param("741.66", 1, ["741.66"], id="single-installment"),
        ],
    )
    def test_installments_add_up_to_the_total(
        self, total: str, count: int, expected: list[str]
    ) -> None:
        """US17-CA02"""
        amounts = split_amount(Decimal(total), count)

        assert amounts == [Decimal(value) for value in expected]
        assert sum(amounts) == Decimal(total)

    def test_installment_below_one_cent_is_refused(self) -> None:
        with pytest.raises(InstallmentBelowOneCentError):
            split_amount(Decimal("0.05"), 6)


class TestMonthlyDueDates:
    def test_one_due_date_per_month_on_the_same_day(self) -> None:
        """US17-CA01"""
        assert monthly_due_dates(date(2026, 11, 10), 3) == [
            date(2026, 11, 10),
            date(2026, 12, 10),
            date(2027, 1, 10),
        ]

    def test_day_missing_in_the_month_moves_to_the_last_day(self) -> None:
        assert monthly_due_dates(date(2026, 1, 31), 4) == [
            date(2026, 1, 31),
            date(2026, 2, 28),
            date(2026, 3, 31),
            date(2026, 4, 30),
        ]
