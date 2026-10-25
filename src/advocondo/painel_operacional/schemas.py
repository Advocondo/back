from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, Field, PlainSerializer

MoneyResponse = Annotated[
    Decimal,
    Field(max_digits=12, decimal_places=2),
    PlainSerializer(lambda value: f"{value:.2f}", return_type=str),
]


class FinancialPeriod(BaseModel):
    month: int
    year: int


class OperationalFinancialSummary(BaseModel):
    goal: MoneyResponse
    accumulated_commission: MoneyResponse
    remaining_to_goal: MoneyResponse
    period: FinancialPeriod


def month_bounds(today: date) -> tuple[date, date]:
    start = today.replace(day=1)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, end
