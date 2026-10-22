import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from advocondo.acordos.models import Agreement
from advocondo.metas.attainment import ONE_CENT
from advocondo.metas.models import Goal
from advocondo.parcelas.models import Installment


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

    def sum_fees_received(
        self, closed_by_id: uuid.UUID, first_day: date, last_day: date
    ) -> Decimal:
        """Honorários das parcelas pagas no período, nos acordos que o colaborador fechou."""
        total = self._session.scalar(
            select(func.coalesce(func.sum(Installment.fee_amount), 0))
            .select_from(Installment)
            .join(Agreement, Agreement.id == Installment.agreement_id)
            .where(
                Agreement.closed_by_id == closed_by_id,
                Installment.payment_date.between(first_day, last_day),
            )
        )
        return (total if total is not None else Decimal(0)).quantize(ONE_CENT)
