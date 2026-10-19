from datetime import date, timedelta
from decimal import Decimal

import pytest

from advocondo.parcelas.errors import (
    FollowingInstallmentWouldBeEmptyError,
    InstallmentBelowOneCentError,
)
from advocondo.parcelas.plan import (
    absorb_difference,
    monthly_due_dates,
    split_amount,
    split_fee,
)

from advocondo.parcelas.status import (
    InstallmentStatus, 
    calculate_installment_status,
)
TODAY = date(2026, 10, 15)

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


class TestAbsorbDifference:
    @pytest.mark.parametrize(
        ("difference", "following", "expected"),
        [
            pytest.param("30.00", ["100.00"] * 3, ["90.00"] * 3, id="higher-amount"),
            pytest.param("-30.00", ["100.00"] * 3, ["110.00"] * 3, id="lower-amount"),
            pytest.param(
                "10.00", ["100.00"] * 3, ["96.67", "96.67", "96.66"], id="cents-to-last"
            ),
            pytest.param(
                "-10.00",
                ["100.00"] * 3,
                ["103.33", "103.33", "103.34"],
                id="negative-cents-to-last",
            ),
        ],
    )
    def test_difference_is_shared_by_the_following_installments(
        self, difference: str, following: list[str], expected: list[str]
    ) -> None:
        """US17-CA03, keeping US17-CA02"""
        new_amounts = absorb_difference(
            Decimal(difference), [Decimal(amount) for amount in following]
        )

        assert new_amounts == [Decimal(amount) for amount in expected]
        assert sum(new_amounts) == sum(Decimal(a) for a in following) - Decimal(
            difference
        )

    def test_following_installment_cannot_be_left_without_value(self) -> None:
        with pytest.raises(FollowingInstallmentWouldBeEmptyError):
            absorb_difference(Decimal("100.00"), [Decimal("50.00"), Decimal("50.00")])


class TestSplitFee:
    @pytest.mark.parametrize(
        ("amounts", "total_fee", "expected"),
        [
            pytest.param(["550.00"] * 10, "550.00", ["55.00"] * 10, id="even"),
            pytest.param(
                ["33.33", "33.33", "33.34"],
                "10.00",
                ["3.33", "3.34", "3.33"],
                id="cents",
            ),
            pytest.param(
                ["100.00", "0.01"], "50.00", ["50.00", "0.00"], id="tiny-last"
            ),
            pytest.param(["100.00", "100.00"], "0.00", ["0.00", "0.00"], id="no-fee"),
            pytest.param(
                ["70.00", "30.00"], "100.00", ["70.00", "30.00"], id="all-fee"
            ),
        ],
    )
    def test_fees_add_up_and_fit_each_installment(
        self, amounts: list[str], total_fee: str, expected: list[str]
    ) -> None:
        """US16-CA01 and US16-CA02"""
        installment_amounts = [Decimal(amount) for amount in amounts]

        fees = split_fee(installment_amounts, Decimal(total_fee))

        assert fees == [Decimal(fee) for fee in expected]
        assert sum(fees) == Decimal(total_fee)
        assert all(
            0 <= fee <= amount
            for fee, amount in zip(fees, installment_amounts, strict=True)
        )
class TestCalculateInstallmentStatus:
    @pytest.mark.parametrize(
        ("days_until_due", "expected"),
        [
            pytest.param(5, InstallmentStatus.OPEN, id="due-in-a-few-days"),
            pytest.param(0, InstallmentStatus.OPEN, id="due-today-not-overdue-yet"),
            pytest.param(-1, InstallmentStatus.OVERDUE, id="due-yesterday"),
            pytest.param(-300, InstallmentStatus.OVERDUE, id="due-long-ago"),
        ],
    )
    def test_unpaid_installment_is_overdue_only_after_the_due_date(
        self, days_until_due: int, expected: InstallmentStatus
    ) -> None:
        """US27-CA01"""
        due_date = TODAY + timedelta(days=days_until_due)

        status = calculate_installment_status(due_date, payment_date=None, today=TODAY)

        assert status == expected

    @pytest.mark.parametrize(
        ("days_until_due", "days_until_payment"),
        [
            pytest.param(5, -5, id="paid-before-the-due-date"),
            pytest.param(0, 0, id="paid-on-the-due-date"),
            pytest.param(-35, -14, id="paid-late-stays-paid"),
        ],
    )
    def test_paid_installment_is_never_overdue(
        self, days_until_due: int, days_until_payment: int
    ) -> None:
        """US27-CA01"""
        due_date = TODAY + timedelta(days=days_until_due)
        payment_date = TODAY + timedelta(days=days_until_payment)

        status = calculate_installment_status(due_date, payment_date, today=TODAY)

        assert status == InstallmentStatus.PAID
