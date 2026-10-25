import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.orm import Session

from advocondo.common.clock import Clock
from advocondo.notificacoes.errors import NotificationNotFoundError
from advocondo.notificacoes.models import Notification
from advocondo.notificacoes.repository import NotificationRepository
from advocondo.users.models import User


@dataclass(frozen=True)
class NotificationPage:
    notifications: Sequence[Notification]
    # Contador do sino: todas as não lidas, não só as desta página.
    unread_count: int


class NotificationService:
    def __init__(
        self, session: Session, notifications: NotificationRepository, clock: Clock
    ) -> None:
        self._session = session
        self._notifications = notifications
        self._clock = clock

    def list_own(self, user: User, limit: int, offset: int) -> NotificationPage:
        """Notificações do próprio usuário, com o contador de não lidas (US30-CA01)."""
        return NotificationPage(
            notifications=self._notifications.list_by_user(user.id, limit, offset),
            unread_count=self._notifications.count_unread(user.id),
        )

    def mark_as_read(self, user: User, notification_id: uuid.UUID) -> Notification:
        """Marca como lida a notificação que o usuário abriu (US30-CA02). A de outro
        usuário é tratada como inexistente, para não revelar que ela existe."""
        notification = self._notifications.get(notification_id)
        if notification is None or notification.user_id != user.id:
            raise NotificationNotFoundError()
        notification.mark_as_read(self._clock.now())
        self._session.commit()
        return notification

    def mark_all_as_read(self, user: User) -> None:
        self._notifications.mark_all_as_read(user.id, self._clock.now())
        self._session.commit()
