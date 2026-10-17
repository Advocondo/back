from sqlalchemy.orm import Session

from advocondo.condominios.errors import CondominiumNotFoundError
from advocondo.condominios.repository import CondominiumRepository
from advocondo.devedores.errors import ContactRequiredError, SimilarDebtorsFoundError
from advocondo.devedores.models import Debtor
from advocondo.devedores.repository import DebtorRepository
from advocondo.devedores.schemas import DebtorCreateRequest
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
