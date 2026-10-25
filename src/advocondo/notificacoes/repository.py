import uuid
from collections.abc import Sequence
from datetime import date, datetime

from sqlalchemy import exists, func, select, update
from sqlalchemy.orm import Session, joinedload, selectinload

from advocondo.acordos.models import Agreement, AgreementStatus
from advocondo.notificacoes.models import Notification
from advocondo.parcelas.models import Installment


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
