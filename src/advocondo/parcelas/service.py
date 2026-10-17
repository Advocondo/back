import uuid
from collections.abc import Sequence

from sqlalchemy.orm import Session

from advocondo.acordos.errors import AgreementNotFoundError
from advocondo.acordos.repository import AgreementRepository
from advocondo.parcelas.models import Installment
from advocondo.parcelas.repository import InstallmentRepository


class InstallmentService:
    def __init__(
        self,
        session: Session,
        installments: InstallmentRepository,
        agreements: AgreementRepository,
    ) -> None:
        self._session = session
        self._installments = installments
        self._agreements = agreements

    def list_plan(self, agreement_id: uuid.UUID) -> Sequence[Installment]:
        """The installments of an agreement, in order."""
        if self._agreements.get(agreement_id) is None:
            raise AgreementNotFoundError()
        return self._installments.list_by_agreement(agreement_id)
