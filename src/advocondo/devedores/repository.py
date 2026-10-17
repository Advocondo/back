import uuid
from collections.abc import Sequence

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from advocondo.common.search import LIKE_ESCAPE_CHARACTER, contains_pattern
from advocondo.devedores.models import Debtor


class DebtorRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, debtor_id: uuid.UUID) -> Debtor | None:
        return self._session.get(Debtor, debtor_id)

    def search(
        self,
        condominium_id: uuid.UUID | None,
        text: str | None,
        limit: int,
        offset: int,
    ) -> Sequence[Debtor]:
        """Debtors whose name or unit contains `text`, optionally of one condominium."""
        query = select(Debtor).order_by(Debtor.name, Debtor.id)
        if condominium_id is not None:
            query = query.where(Debtor.condominium_id == condominium_id)
        if text:
            pattern = contains_pattern(text)
            query = query.where(
                or_(
                    Debtor.name.ilike(pattern, escape=LIKE_ESCAPE_CHARACTER),
                    Debtor.unit.ilike(pattern, escape=LIKE_ESCAPE_CHARACTER),
                )
            )
        return self._session.scalars(query.limit(limit).offset(offset)).all()

    def list_by_condominium(self, condominium_id: uuid.UUID) -> Sequence[Debtor]:
        return self._session.scalars(
            select(Debtor).where(Debtor.condominium_id == condominium_id)
        ).all()

    def save(self, debtor: Debtor) -> None:
        """Inserts a new debtor or writes the changes of an existing one."""
        self._session.add(debtor)
        self._session.flush()
