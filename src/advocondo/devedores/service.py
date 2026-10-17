import uuid
from collections.abc import Sequence

from sqlalchemy.orm import Session

from advocondo.condominios.errors import CondominiumNotFoundError
from advocondo.condominios.repository import CondominiumRepository
from advocondo.devedores.errors import (
    ContactRequiredError,
    DebtorNotFoundError,
    SimilarDebtorsFoundError,
)
from advocondo.devedores.models import Debtor
from advocondo.devedores.repository import DebtorRepository
from advocondo.devedores.schemas import DebtorCreateRequest, DebtorUpdateRequest
from advocondo.devedores.similarity import find_similar_debtors


class DebtorService:
    def __init__(
        self,
        session: Session,
        debtors: DebtorRepository,
        condominiums: CondominiumRepository,
    ) -> None:
        self._session = session
        self._debtors = debtors
        self._condominiums = condominiums

    def register(self, request: DebtorCreateRequest) -> Debtor:
        """Registers a debtor once, to be reused in every agreement with them."""
        if self._condominiums.get(request.condominium_id) is None:
            raise CondominiumNotFoundError()
        ensure_has_a_contact(request.phone, request.email)
        if not request.confirm_duplicate:
            self._warn_about_similar_debtors(request)

        debtor = Debtor(**request.model_dump(exclude={"confirm_duplicate"}))
        self._debtors.save(debtor)
        self._session.commit()
        return debtor

    def get(self, debtor_id: uuid.UUID) -> Debtor:
        debtor = self._debtors.get(debtor_id)
        if debtor is None:
            raise DebtorNotFoundError()
        return debtor

    def search(
        self,
        condominium_id: uuid.UUID | None,
        text: str | None,
        limit: int,
        offset: int,
    ) -> Sequence[Debtor]:
        search_text = text.strip() if text else None
        return self._debtors.search(condominium_id, search_text or None, limit, offset)

    def update(self, debtor_id: uuid.UUID, request: DebtorUpdateRequest) -> Debtor:
        debtor = self.get(debtor_id)
        changes = request.model_dump(exclude_unset=True)
        ensure_has_a_contact(
            changes.get("phone", debtor.phone), changes.get("email", debtor.email)
        )
        for field_name, new_value in changes.items():
            setattr(debtor, field_name, new_value)
        self._debtors.save(debtor)
        self._session.commit()
        return debtor

    def _warn_about_similar_debtors(self, request: DebtorCreateRequest) -> None:
        similar_debtors = find_similar_debtors(
            request.name,
            request.unit,
            self._debtors.list_by_condominium(request.condominium_id),
        )
        if similar_debtors:
            raise SimilarDebtorsFoundError(similar_debtors)


def ensure_has_a_contact(phone: str | None, email: str | None) -> None:
    if phone is None and email is None:
        raise ContactRequiredError()
