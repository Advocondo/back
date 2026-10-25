import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from advocondo.acordos.models import Agreement
from advocondo.parcelas.models import Installment


class OperationalPanelRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def accumulated_commission(
        self, user_id: uuid.UUID, period_start: date, period_end: date
    ) -> Decimal:
        """Sum only paid office-fee installments assigned to this operator."""
        amount = self._session.scalar(
            select(func.coalesce(func.sum(Installment.fee_amount), 0))
            .join(Agreement, Agreement.id == Installment.agreement_id)
            .where(
                Agreement.responsible_lawyer_id == user_id,
                Installment.payment_date >= period_start,
                Installment.payment_date < period_end,
            )
        )
        return Decimal(amount or 0)
