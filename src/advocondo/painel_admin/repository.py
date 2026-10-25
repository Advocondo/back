import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from advocondo.acordos.models import Agreement, AgreementStatus
from advocondo.condominios.models import Condominium
from advocondo.devedores.models import Debtor
from advocondo.painel_admin.export import ExportableInstallmentRow
from advocondo.parcelas.models import Installment
from advocondo.parcelas.status import InstallmentStatus
from advocondo.users.models import Role, User


class AdminPanelRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def office_total_revenue(self, period_start: date, period_end: date) -> Decimal:
        """Office fees received in the period, including unassigned agreements."""
        amount = self._session.scalar(
            select(func.coalesce(func.sum(Installment.fee_amount), 0)).where(
                Installment.payment_date >= period_start,
                Installment.payment_date < period_end,
            )
        )
        return Decimal(amount or 0)

    def team_commissions(
        self, period_start: date, period_end: date
    ) -> list[tuple[uuid.UUID, str, Decimal]]:
        """Monthly paid fees by current Operator, including members with zero."""
        commission = func.coalesce(func.sum(Installment.fee_amount), 0)
        rows = self._session.execute(
            select(User.id, User.name, commission)
            .select_from(User)
            .outerjoin(Agreement, Agreement.responsible_lawyer_id == User.id)
            .outerjoin(
                Installment,
                (Installment.agreement_id == Agreement.id)
                & (Installment.payment_date >= period_start)
                & (Installment.payment_date < period_end),
            )
            .where(User.role == Role.OPERATOR)
            .group_by(User.id, User.name)
            .order_by(User.name, User.id)
        )
        return [
            (user_id, name, Decimal(amount or 0))
            for user_id, name, amount in rows.all()
        ]

    def count_active_agreements(self) -> int:
        count = self._session.scalar(
            select(func.count(Agreement.id)).where(
                Agreement.status == AgreementStatus.ACTIVE
            )
        )
        return int(count or 0)

    def count_installments_due(self, period_start: date, period_end: date) -> int:
        count = self._session.scalar(
            select(func.count(Installment.id)).where(
                Installment.due_date >= period_start,
                Installment.due_date < period_end,
            )
        )
        return int(count or 0)

    def count_overdue_installments_at(
        self,
        period_start: date,
        period_end: date,
        as_of_date: date,
    ) -> int:
        """Unpaid installments due in the period and overdue on `as_of_date`."""
        count = self._session.scalar(
            select(func.count(Installment.id)).where(
                Installment.due_date >= period_start,
                Installment.due_date < period_end,
                Installment.due_date < as_of_date,
                or_(
                    Installment.payment_date.is_(None),
                    Installment.payment_date > as_of_date,
                ),
            )
        )
        return int(count or 0)

    def paid_commissions(self, period_start: date, period_end: date) -> Decimal:
        """Paid office fees in the period, regardless of lawyer assignment."""
        amount = self._session.scalar(
            select(func.coalesce(func.sum(Installment.fee_amount), 0)).where(
                Installment.payment_date >= period_start,
                Installment.payment_date < period_end,
            )
        )
        return Decimal(amount or 0)

    def list_installments_for_export(
        self,
        period_start: date,
        period_end: date,
        as_of_date: date,
        *,
        condominium_id: uuid.UUID | None = None,
        responsible_lawyer_id: uuid.UUID | None = None,
        status: InstallmentStatus | None = None,
    ) -> list[ExportableInstallmentRow]:
        query = (
            select(
                Condominium.name,
                Debtor.name,
                Debtor.unit,
                Agreement.id,
                Installment.number,
                Installment.due_date,
                Installment.payment_date,
                Installment.amount,
                Installment.fee_amount,
                User.name,
            )
            .join(Agreement, Agreement.id == Installment.agreement_id)
            .join(Condominium, Condominium.id == Agreement.condominium_id)
            .join(Debtor, Debtor.id == Agreement.debtor_id)
            .outerjoin(User, User.id == Agreement.responsible_lawyer_id)
            .where(
                Installment.due_date >= period_start,
                Installment.due_date < period_end,
            )
        )
        if condominium_id is not None:
            query = query.where(Agreement.condominium_id == condominium_id)
        if responsible_lawyer_id is not None:
            query = query.where(
                Agreement.responsible_lawyer_id == responsible_lawyer_id
            )
        if status == InstallmentStatus.PAID:
            query = query.where(Installment.payment_date.is_not(None))
        elif status == InstallmentStatus.OVERDUE:
            query = query.where(
                Installment.payment_date.is_(None),
                Installment.due_date < as_of_date,
            )
        elif status == InstallmentStatus.OPEN:
            query = query.where(
                Installment.payment_date.is_(None),
                Installment.due_date >= as_of_date,
            )

        rows = self._session.execute(
            query.order_by(
                Installment.due_date,
                Condominium.name,
                Debtor.name,
                Installment.number,
                Agreement.id,
            )
        )
        export_rows: list[ExportableInstallmentRow] = []
        for row in rows.all():
            payment_date = row[6]
            due_date = row[5]
            export_rows.append(
                ExportableInstallmentRow(
                    condominium_name=row[0],
                    debtor_name=row[1],
                    debtor_unit=row[2],
                    agreement_id=str(row[3]),
                    installment_number=row[4],
                    due_date=due_date,
                    payment_date=payment_date,
                    status=(
                        InstallmentStatus.PAID
                        if payment_date is not None
                        else InstallmentStatus.OVERDUE
                        if due_date < as_of_date
                        else InstallmentStatus.OPEN
                    ),
                    amount=row[7],
                    fee_amount=row[8],
                    responsible_lawyer_name=row[9],
                )
            )
        return export_rows
