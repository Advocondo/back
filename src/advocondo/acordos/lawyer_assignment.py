__all__ = [
    "LawyerAssignmentService",
    "LawyerNotEligibleError",
    "ensure_can_be_responsible",
]
import uuid
from collections.abc import Sequence

from sqlalchemy.orm import Session

from advocondo.acordos.errors import (
    AgreementCancelledError,
    AgreementNotFoundError,
    LawyerNotEligibleError,
    LawyerNotFoundError,
)
from advocondo.acordos.models import Agreement, AgreementStatus, LawyerAssignment
from advocondo.acordos.repository import AgreementRepository
from advocondo.common.clock import Clock
from advocondo.users.models import User
from advocondo.users.repository import UserRepository


class LawyerAssignmentService:
    def __init__(
        self,
        session: Session,
        agreements: AgreementRepository,
        users: UserRepository,
        clock: Clock,
    ) -> None:
        self._session = session
        self._agreements = agreements
        self._users = users
        self._clock = clock

    def assign(
        self, agreement_id: uuid.UUID, lawyer_id: uuid.UUID, assigned_by: User
    ) -> Agreement:
        """Atribui o acordo a um advogado, ou troca o responsável (US18)."""
        agreement = self._agreements.get(agreement_id)
        if agreement is None:
            raise AgreementNotFoundError()
        if agreement.status == AgreementStatus.CANCELLED:
            raise AgreementCancelledError()
        lawyer = self._users.get_by_id(lawyer_id)
        if lawyer is None:
            raise LawyerNotFoundError()
        ensure_can_be_responsible(lawyer)

        if agreement.assign_lawyer(lawyer, assigned_by, self._clock.now()):
            self._agreements.save(agreement)
            self._session.commit()
        return agreement

    def history(self, agreement_id: uuid.UUID) -> Sequence[LawyerAssignment]:
        """Atribuições do acordo, da mais antiga para a mais recente."""
        agreement = self._agreements.get(agreement_id)
        if agreement is None:
            raise AgreementNotFoundError()
        return agreement.lawyer_assignments


def ensure_can_be_responsible(lawyer: User) -> None:
    """Só advogado ativo, com OAB, pode responder por um acordo (US18-CA01)."""
    if not lawyer.can_be_responsible_lawyer:
        raise LawyerNotEligibleError()
