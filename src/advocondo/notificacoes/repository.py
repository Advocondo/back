import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from advocondo.condominios.models import Condominium
from advocondo.notificacoes.models import (
    ClientNotificationEvent,
    ClientNotificationLog,
)
from advocondo.users.models import Role, User, UserCondominium, UserStatus


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
        return self._session.execute(query).tuples().all()

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
