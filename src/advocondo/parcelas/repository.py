import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from sqlalchemy import ColumnElement, and_, or_, select
from sqlalchemy.orm import Session, contains_eager

from advocondo.acordos.models import Agreement, AgreementStatus
from advocondo.parcelas.models import Installment
from advocondo.parcelas.status import InstallmentStatus


@dataclass(frozen=True)
class InstallmentFilters:
    """Filtros da listagem do mês (US25-CA02). Os que ficam None não são
    aplicados."""

    condominium_id: uuid.UUID | None = None
    responsible_lawyer_id: uuid.UUID | None = None
    status: InstallmentStatus | None = None


class InstallmentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, installment_id: uuid.UUID) -> Installment | None:
        return self._session.get(Installment, installment_id)

    def get_for_update(self, installment_id: uuid.UUID) -> Installment | None:
        """Carrega a parcela e trava a linha até o fim da transação."""
        return self._session.scalar(
            select(Installment)
            .where(Installment.id == installment_id)
            .with_for_update()
        )

    def list_by_agreement(self, agreement_id: uuid.UUID) -> Sequence[Installment]:
        return self._session.scalars(
            select(Installment)
            .where(Installment.agreement_id == agreement_id)
            .order_by(Installment.number)
        ).all()

    def search_due_between(
        self,
        first_day: date,
        last_day: date,
        filters: InstallmentFilters,
        today: date,
        limit: int,
        offset: int,
    ) -> Sequence[Installment]:
        """Parcelas que vencem entre os dois dias, inclusive, da que vence primeiro
        para a última. O acordo vem na mesma consulta, com o devedor e o
        condomínio. As parcelas sem pagamento de acordo cancelado ficam de fora
        (US20); as pagas continuam, porque o histórico segue consultável."""
        query = (
            select(Installment)
            .join(Installment.agreement)
            .options(contains_eager(Installment.agreement))
            .where(Installment.due_date.between(first_day, last_day))
            .where(
                or_(
                    Installment.payment_date.is_not(None),
                    Agreement.status != AgreementStatus.CANCELLED,
                )
            )
            .order_by(Installment.due_date, Installment.id)
        )
        if filters.condominium_id is not None:
            query = query.where(Agreement.condominium_id == filters.condominium_id)
        if filters.responsible_lawyer_id is not None:
            query = query.where(
                Agreement.responsible_lawyer_id == filters.responsible_lawyer_id
            )
        if filters.status is not None:
            query = query.where(has_status(filters.status, today))
        return self._session.scalars(query.limit(limit).offset(offset)).all()

    def search_paid_without_invoice(
        self, limit: int, offset: int
    ) -> Sequence[Installment]:
        """Parcelas pagas sem nota fiscal, da baixa mais antiga para a mais recente.
        O acordo vem na mesma consulta, com o devedor e o condomínio."""
        query = (
            select(Installment)
            .join(Installment.agreement)
            .options(contains_eager(Installment.agreement))
            .where(
                Installment.payment_date.is_not(None),
                Installment.invoice_number.is_(None),
            )
            .order_by(Installment.payment_date, Installment.id)
        )
        return self._session.scalars(query.limit(limit).offset(offset)).all()


def has_status(status: InstallmentStatus, today: date) -> ColumnElement[bool]:
    """A regra de `calculate_installment_status` escrita em SQL, para a listagem
    filtrar e paginar no banco. Os testes garantem que as duas sempre concordam."""
    if status == InstallmentStatus.PAID:
        return Installment.payment_date.is_not(None)
    if status == InstallmentStatus.OVERDUE:
        return and_(Installment.payment_date.is_(None), Installment.due_date < today)
    return and_(Installment.payment_date.is_(None), Installment.due_date >= today)
