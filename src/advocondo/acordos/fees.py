"""The office's fee on an agreement (US16)."""

from decimal import ROUND_HALF_UP, Decimal

ONE_CENT = Decimal("0.01")


def fee_from_percentage(total_amount: Decimal, fee_percentage: Decimal) -> Decimal:
    """Fee in reais for a percentage of the total, rounded to the nearest cent."""
    return (total_amount * fee_percentage / 100).quantize(ONE_CENT, ROUND_HALF_UP)
