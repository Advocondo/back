import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from advocondo.devedores.models import Debtor


class DebtorRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_condominium(self, condominium_id: uuid.UUID) -> Sequence[Debtor]:
        return self._session.scalars(
            select(Debtor).where(Debtor.condominium_id == condominium_id)
        ).all()

    def save(self, debtor: Debtor) -> None:
        """Inserts a new debtor or writes the changes of an existing one."""
        self._session.add(debtor)
        self._session.flush()
