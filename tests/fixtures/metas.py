from decimal import Decimal
from typing import Protocol

import pytest
from sqlalchemy.orm import Session

from advocondo.metas.models import Goal
from advocondo.users.models import User


class CreateGoal(Protocol):
    def __call__(
        self,
        user: User,
        year: int = ...,
        month: int = ...,
        target_amount: Decimal = ...,
    ) -> Goal: ...


@pytest.fixture
def create_goal(db_session: Session) -> CreateGoal:
    """Grava uma meta direto no banco; por padrão, março de 2026."""

    def create(
        user: User,
        year: int = 2026,
        month: int = 3,
        target_amount: Decimal = Decimal("5000.00"),
    ) -> Goal:
        goal = Goal(
            user_id=user.id, year=year, month=month, target_amount=target_amount
        )
        db_session.add(goal)
        db_session.flush()
        return goal

    return create