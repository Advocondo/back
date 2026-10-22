"""Regras puras do atingimento da meta (US36)."""

import calendar
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from advocondo.metas.models import Goal

ONE_CENT = Decimal("0.01")
PERCENT = 100


@dataclass(frozen=True)
class GoalProgress:
    """A meta do mês, o que o colaborador já alcançou e quanto isso representa dela."""

    goal: Goal
    achieved_amount: Decimal
    attainment_percentage: Decimal


def month_range(year: int, month: int) -> tuple[date, date]:
    """Primeiro e último dia do mês."""
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def calculate_attainment_percentage(
    achieved_amount: Decimal, target_amount: Decimal
) -> Decimal:
    """Percentual da meta alcançado, com 2 casas. Passa de 100 quando a meta é superada."""
    return (achieved_amount / target_amount * PERCENT).quantize(ONE_CENT, ROUND_HALF_UP)
