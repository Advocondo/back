import uuid
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


class TeamCommission(BaseModel):
    user_id: uuid.UUID
    user_name: str
    commission: MoneyResponse


class AdminFinancialSummary(BaseModel):
    office_total_revenue: MoneyResponse
    team_commissions: list[TeamCommission]
    period: FinancialPeriod


PercentResponse = Annotated[
    Decimal,
    Field(ge=0, le=100, max_digits=5, decimal_places=2),
    PlainSerializer(lambda value: float(value), return_type=float),
]


class AdminDashboardSummary(BaseModel):
    active_agreements: int
    monthly_default_rate: PercentResponse
    overdue_installments: int
    installments_due: int
    paid_commissions: MoneyResponse
    period: FinancialPeriod


def month_bounds(today: date) -> tuple[date, date]:
    start = today.replace(day=1)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, end
