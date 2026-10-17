"""Pure rules of the installment plan: amounts in cents and monthly due dates."""

import calendar
from datetime import date
from decimal import Decimal

from advocondo.parcelas.errors import (
    FollowingInstallmentWouldBeEmptyError,
    InstallmentBelowOneCentError,
)

CENTS_PER_REAL = 100


def to_cents(amount: Decimal) -> int:
    return int(amount * CENTS_PER_REAL)


def from_cents(cents: int) -> Decimal:
    return Decimal(cents) / CENTS_PER_REAL


def split_amount(total: Decimal, installment_count: int) -> list[Decimal]:
    """Equal installments; the cents that do not divide evenly go to the last one,
    so the installments always add up to the total (US17-CA02)."""
    total_cents = to_cents(total)
    base_cents = total_cents // installment_count
    if base_cents == 0:
        raise InstallmentBelowOneCentError()
    amounts = [base_cents] * installment_count
    amounts[-1] += total_cents - base_cents * installment_count
    return [from_cents(cents) for cents in amounts]


def monthly_due_dates(first_due_date: date, installment_count: int) -> list[date]:
    """One due date per month on the same day as the first one; in months without
    that day (e.g. the 31st in April), on the last day of the month."""
    return [add_months(first_due_date, months) for months in range(installment_count)]


def add_months(start: date, months: int) -> date:
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    last_day_of_month = calendar.monthrange(year, month)[1]
    return date(year, month, min(start.day, last_day_of_month))


def absorb_difference(
    difference: Decimal, following_amounts: list[Decimal]
) -> list[Decimal]:
    """New amounts of the following open installments after one installment changed
    by `difference`, so the plan keeps adding up to the total (US17-CA02, CA03).

    The difference is shared equally; the cents left over go to the last one.
    """
    difference_cents = to_cents(difference)
    count = len(following_amounts)
    share_cents = int(difference_cents / count)  # rounds toward zero, for both signs
    shares = [share_cents] * count
    shares[-1] += difference_cents - share_cents * count

    new_amounts_cents = [
        to_cents(amount) - share
        for amount, share in zip(following_amounts, shares, strict=True)
    ]
    if any(cents <= 0 for cents in new_amounts_cents):
        raise FollowingInstallmentWouldBeEmptyError()
    return [from_cents(cents) for cents in new_amounts_cents]
