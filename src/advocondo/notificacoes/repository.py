import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from advocondo.condominios.models import Condominium
from advocondo.notificacoes.models import ClientNotificationLog
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
