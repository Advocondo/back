import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.orm import Session

from advocondo.common.clock import Clock
from advocondo.common.email import EmailMessage, EmailSender
from advocondo.notificacoes.errors import NotificationNotFoundError
from advocondo.notificacoes.models import (
    ClientNotificationEvent,
    ClientNotificationLog,
    Notification,
)
from advocondo.notificacoes.repository import (
    ClientNotificationRepository,
    NotificationRepository,
)
from advocondo.users.models import User

logger = logging.getLogger(__name__)


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


class ClientNotificationService:
    def __init__(
        self,
        session: Session,
        notifications: ClientNotificationRepository,
        email_sender: EmailSender,
        clock: Clock,
        frontend_url: str,
    ) -> None:
        self._session = session
        self._notifications = notifications
        self._email_sender = email_sender
        self._clock = clock
        self._frontend_url = frontend_url.rstrip("/")

    def send_condominium_update(
        self,
        condominium_id: uuid.UUID,
        event_type: ClientNotificationEvent,
        message: str,
        link: str | None = None,
        *,
        include_frontend_link: bool = True,
        skip_already_sent: bool = False,
    ) -> None:
        """Notify active Clients linked to the condominium and log each delivery.

        Callers invoke this only after committing the business event. E-mail or log
        failures are reported, but never roll back or fail the completed operation.
        """
        recipients = self._notifications.list_active_clients(condominium_id)
        email_link = (link or self._frontend_url) if include_frontend_link else None
        for user, condominium_name in recipients:
            if skip_already_sent and self._notifications.was_sent(
                user.id, condominium_id, event_type, message
            ):
                continue
            email = build_condominium_update_email(
                user.name,
                user.email,
                condominium_name,
                message,
                email_link,
            )
            try:
                self._email_sender.send(email)
            except Exception:
                logger.exception(
                    "Falha ao enviar notificação do condomínio para Cliente %s",
                    user.id,
                )
                continue

            notification = ClientNotificationLog(
                user_id=user.id,
                condominium_id=condominium_id,
                event_type=event_type,
                message=message,
                link=email_link,
                sent_at=self._clock.now(),
            )
            try:
                self._notifications.save(notification)
                self._session.commit()
            except Exception:
                self._session.rollback()
                logger.exception(
                    "Falha ao registrar notificação enviada do condomínio %s",
                    condominium_id,
                )


def build_condominium_update_email(
    client_name: str,
    email: str,
    condominium_name: str,
    message: str,
    link: str | None,
) -> EmailMessage:
    body = f"Olá, {client_name}.\n\n{message}\n\nCondomínio: {condominium_name}\n"
    if link is not None:
        body += f"\nAcesse o painel do cliente: {link}\n"
    return EmailMessage(
        to=email,
        subject=f"Atualização do condomínio {condominium_name}",
        body=body,
    )
