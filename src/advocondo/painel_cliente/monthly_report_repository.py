import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from advocondo.acordos.models import Agreement, AgreementStatus
from advocondo.condominios.models import Condominium
from advocondo.painel_cliente.models import CondominiumMonthlyReport
from advocondo.users.models import Role, User, UserCondominium, UserStatus


class CondominiumMonthlyReportRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_condominiums_with_active_clients(self) -> Sequence[Condominium]:
        query = (
            select(Condominium)
            .join(UserCondominium, UserCondominium.condominium_id == Condominium.id)
            .join(User, User.id == UserCondominium.user_id)
            .where(User.role == Role.CLIENT, User.status == UserStatus.ACTIVE)
            .distinct()
            .order_by(Condominium.name, Condominium.id)
        )
        return self._session.scalars(query).all()

    def list_active_agreements(self, condominium_id: uuid.UUID) -> Sequence[Agreement]:
        query = (
            select(Agreement)
            .where(
                Agreement.condominium_id == condominium_id,
                Agreement.status == AgreementStatus.ACTIVE,
            )
            .order_by(Agreement.id)
            .options(selectinload(Agreement.installments))
        )
        return self._session.scalars(query).all()

    def get(
        self, condominium_id: uuid.UUID, year: int, month: int
    ) -> CondominiumMonthlyReport | None:
        query = select(CondominiumMonthlyReport).where(
            CondominiumMonthlyReport.condominium_id == condominium_id,
            CondominiumMonthlyReport.year == year,
            CondominiumMonthlyReport.month == month,
        )
        return self._session.scalar(query)

    def get_for_client(
        self,
        user_id: uuid.UUID,
        condominium_id: uuid.UUID,
        year: int,
        month: int,
    ) -> CondominiumMonthlyReport | None:
        query = (
            select(CondominiumMonthlyReport)
            .join(
                UserCondominium,
                UserCondominium.condominium_id
                == CondominiumMonthlyReport.condominium_id,
            )
            .where(
                UserCondominium.user_id == user_id,
                CondominiumMonthlyReport.condominium_id == condominium_id,
                CondominiumMonthlyReport.year == year,
                CondominiumMonthlyReport.month == month,
            )
        )
        return self._session.scalar(query)

    def save(self, report: CondominiumMonthlyReport) -> None:
        self._session.add(report)
        self._session.flush()
