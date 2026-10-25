from decimal import Decimal

from advocondo.common.clock import Clock, today_in_brazil
from advocondo.painel_operacional.repository import OperationalPanelRepository
from advocondo.painel_operacional.schemas import (
    FinancialPeriod,
    OperationalFinancialSummary,
    month_bounds,
)
from advocondo.users.models import User


class OperationalPanelService:
    def __init__(self, repository: OperationalPanelRepository, clock: Clock) -> None:
        self._repository = repository
        self._clock = clock

    def get_financial_summary(self, user: User) -> OperationalFinancialSummary:
        today = today_in_brazil(self._clock.now())
        start, end = month_bounds(today)
        accumulated = self._repository.accumulated_commission(user.id, start, end)
        goal = user.monthly_goal
        return OperationalFinancialSummary(
            goal=goal,
            accumulated_commission=accumulated,
            remaining_to_goal=max(goal - accumulated, Decimal("0.00")),
            period=FinancialPeriod(month=today.month, year=today.year),
        )
