import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from advocondo.acordos.models import Agreement, AgreementStatus


@dataclass(frozen=True)
class AgreementFilters:
    """Filters left as None are not applied."""

    status: AgreementStatus | None = None
    condominium_id: uuid.UUID | None = None
    debtor_id: uuid.UUID | None = None


class AgreementRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, agreement_id: uuid.UUID) -> Agreement | None:
        return self._session.get(Agreement, agreement_id)

    def search(
        self, filters: AgreementFilters, limit: int, offset: int
    ) -> Sequence[Agreement]:
        """Newest agreements first."""
        query = select(Agreement).order_by(Agreement.created_at.desc(), Agreement.id)
        if filters.status is not None:
            query = query.where(Agreement.status == filters.status)
        if filters.condominium_id is not None:
            query = query.where(Agreement.condominium_id == filters.condominium_id)
        if filters.debtor_id is not None:
            query = query.where(Agreement.debtor_id == filters.debtor_id)
        return self._session.scalars(query.limit(limit).offset(offset)).all()

    def save(self, agreement: Agreement) -> None:
        """Inserts a new agreement or writes the changes of an existing one."""
        self._session.add(agreement)
        self._session.flush()
