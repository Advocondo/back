from decimal import Decimal

from advocondo.common.clock import Clock, today_in_brazil
from advocondo.metas.repository import GoalRepository
from advocondo.painel_operacional.repository import OperationalPanelRepository
from advocondo.painel_operacional.schemas import (
    FinancialPeriod,
    OperationalFinancialSummary,
    month_bounds,
)
from advocondo.users.models import User


class OperationalPanelService:
    def __init__(
        self,
        repository: OperationalPanelRepository,
        goals: GoalRepository,
        clock: Clock,
    ) -> None:
        self._repository = repository
        self._goals = goals
        self._clock = clock

    def get_financial_summary(self, user: User) -> OperationalFinancialSummary:
        """A meta é a do mês atual definida pelo Administrador na US36; sem meta
        definida, `goal` e `remaining_to_goal` vêm vazios."""
        today = today_in_brazil(self._clock.now())
        start, end = month_bounds(today)
        accumulated = self._repository.accumulated_commission(user.id, start, end)
        goal = self._goals.get(user.id, today.year, today.month)
        target = goal.target_amount if goal is not None else None
        return OperationalFinancialSummary(
            goal=target,
            accumulated_commission=accumulated,
            remaining_to_goal=(
                max(target - accumulated, Decimal("0.00"))
                if target is not None
                else None
            ),
            period=FinancialPeriod(month=today.month, year=today.year),
        )
