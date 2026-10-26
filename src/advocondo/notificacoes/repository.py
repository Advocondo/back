import uuid
from collections.abc import Sequence
from datetime import date, datetime

from sqlalchemy import exists, func, select, update
from sqlalchemy.orm import Session, joinedload, selectinload

from advocondo.acordos.models import Agreement, AgreementStatus
from advocondo.condominios.models import Condominium
from advocondo.notificacoes.models import (
    ClientNotificationEvent,
    ClientNotificationLog,
    Notification,
)
from advocondo.parcelas.models import Installment
from advocondo.users.models import Role, User, UserCondominium, UserStatus


class NotificationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add_all(self, notifications: Sequence[Notification]) -> None:
        self._session.add_all(notifications)
        self._session.flush()

    def get(self, notification_id: uuid.UUID) -> Notification | None:
        return self._session.get(Notification, notification_id)

    def list_by_user(
        self, user_id: uuid.UUID, limit: int, offset: int
    ) -> Sequence[Notification]:
        """Notificações do usuário, da mais recente para a mais antiga, com a parcela,
        o acordo e o devedor já carregados."""
        return self._session.scalars(
            select(Notification)
            .where(Notification.user_id == user_id)
            .options(
                joinedload(Notification.installment)
                .joinedload(Installment.agreement)
                .selectinload(Agreement.installments)
            )
            .order_by(Notification.created_at.desc(), Notification.id)
            .limit(limit)
            .offset(offset)
        ).all()

    def count_unread(self, user_id: uuid.UUID) -> int:
        return (
            self._session.scalar(
                select(func.count())
                .select_from(Notification)
                .where(Notification.user_id == user_id, Notification.read_at.is_(None))
            )
            or 0
        )

    def mark_all_as_read(self, user_id: uuid.UUID, now: datetime) -> None:
        self._session.execute(
            update(Notification)
            .where(Notification.user_id == user_id, Notification.read_at.is_(None))
            .values(read_at=now)
        )

    def list_overdue_installments_without_notification(
        self, today: date
    ) -> Sequence[Installment]:
        """Parcelas atrasadas em `today` que ainda não geraram notificação, com o
        acordo e o advogado responsável carregados. A regra de atraso é a da US27;
        as parcelas de acordo cancelado saem da cobrança (US20)."""
        already_notified = exists().where(Notification.installment_id == Installment.id)
        return self._session.scalars(
            select(Installment)
            .join(Installment.agreement)
            .options(selectinload(Installment.agreement))
            .where(
                Installment.payment_date.is_(None),
                Installment.due_date < today,
                Agreement.status != AgreementStatus.CANCELLED,
                ~already_notified,
            )
            .order_by(Installment.due_date, Installment.id)
        ).all()


class ClientNotificationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_active_clients(
        self, condominium_id: uuid.UUID
    ) -> Sequence[tuple[User, str]]:
        query = (
            select(User, Condominium.name)
            .join(UserCondominium, UserCondominium.user_id == User.id)
            .join(Condominium, Condominium.id == UserCondominium.condominium_id)
            .where(
                UserCondominium.condominium_id == condominium_id,
                User.role == Role.CLIENT,
                User.status == UserStatus.ACTIVE,
            )
            .order_by(User.id)
        )
        return self._session.execute(query).all()

    def save(self, notification: ClientNotificationLog) -> None:
        self._session.add(notification)
        self._session.flush()

    def was_sent(
        self,
        user_id: uuid.UUID,
        condominium_id: uuid.UUID,
        event_type: ClientNotificationEvent,
        message: str,
    ) -> bool:
        query = select(ClientNotificationLog.id).where(
            ClientNotificationLog.user_id == user_id,
            ClientNotificationLog.condominium_id == condominium_id,
            ClientNotificationLog.event_type == event_type,
            ClientNotificationLog.message == message,
        )
        return self._session.scalar(query) is not None
