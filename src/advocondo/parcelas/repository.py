import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from advocondo.parcelas.models import Installment


class InstallmentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, installment_id: uuid.UUID) -> Installment | None:
        return self._session.get(Installment, installment_id)

    def list_by_agreement(self, agreement_id: uuid.UUID) -> Sequence[Installment]:
        return self._session.scalars(
            select(Installment)
            .where(Installment.agreement_id == agreement_id)
            .order_by(Installment.number)
        ).all()
