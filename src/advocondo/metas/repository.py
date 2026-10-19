import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from advocondo.metas.models import Goal


class GoalRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, user_id: uuid.UUID, year: int, month: int) -> Goal | None:
        return self._session.scalar(
            select(Goal).where(
                Goal.user_id == user_id, Goal.year == year, Goal.month == month
            )
        )

    def save(self, goal: Goal) -> None:
        """Insere a meta nova ou grava as mudanças de uma que já existe."""
        self._session.add(goal)
        self._session.flush()
