import uuid

from sqlalchemy.orm import Session

from advocondo.metas.attainment import (
    GoalProgress,
    calculate_attainment_percentage,
    month_range,
)
from advocondo.metas.errors import (
    CollaboratorNotFoundError,
    GoalNotFoundError,
    GoalOnlyForOperatorsError,
)
from advocondo.metas.models import Goal
from advocondo.metas.repository import GoalRepository
from advocondo.metas.schemas import GoalRequest
from advocondo.users.models import Role
from advocondo.users.repository import UserRepository


class GoalService:
    def __init__(
        self, session: Session, goals: GoalRepository, users: UserRepository
    ) -> None:
        self._session = session
        self._goals = goals
        self._users = users

    def define(
        self, user_id: uuid.UUID, year: int, month: int, request: GoalRequest
    ) -> Goal:
        """Define a meta do mês de um colaborador, ou altera a que já existe."""
        collaborator = self._users.get_by_id(user_id)
        if collaborator is None:
            raise CollaboratorNotFoundError()
        ensure_role_can_have_goal(collaborator.role)
        goal = self._goals.get(user_id, year, month)
        if goal is None:
            goal = Goal(user_id=user_id, year=year, month=month)
        goal.target_amount = request.target_amount
        # Duas requisições simultâneas para o mesmo colaborador e mês passam por
        # esta checagem juntas; a restrição UNIQUE do banco impede a meta duplicada.
        self._goals.save(goal)
        self._session.commit()
        return goal

    def get_own(self, user_id: uuid.UUID, year: int, month: int) -> Goal:
        """Meta do mês do próprio colaborador."""
        goal = self._goals.get(user_id, year, month)
        if goal is None:
            raise GoalNotFoundError()
        return goal

    def get_own_progress(
        self, user_id: uuid.UUID, year: int, month: int
    ) -> GoalProgress:
        """Meta do mês do próprio colaborador e quanto dela já foi alcançado (US36)."""
        goal = self.get_own(user_id, year, month)
        first_day, last_day = month_range(year, month)
        achieved = self._goals.sum_fees_received(user_id, first_day, last_day)
        percentage = calculate_attainment_percentage(achieved, goal.target_amount)
        return GoalProgress(goal, achieved, percentage)


def ensure_role_can_have_goal(role: Role) -> None:
    """Só a Equipe Operacional tem meta: o Cliente não vê esses dados."""
    if role != Role.OPERATOR:
        raise GoalOnlyForOperatorsError()
