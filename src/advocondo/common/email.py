import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage as MimeMessage
from typing import Protocol

from advocondo.config import Settings, get_settings

logger = logging.getLogger(__name__)

SMTP_TIMEOUT_SECONDS = 10
LOCAL_ENVIRONMENT = "local"


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    body: str


class EmailSender(Protocol):
    def send(self, message: EmailMessage) -> None: ...


class SmtpEmailSender:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
        use_tls: bool,
        sender: str,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._use_tls = use_tls
        self._sender = sender

    def send(self, message: EmailMessage) -> None:
        mime_message = MimeMessage()
        mime_message["From"] = self._sender
        mime_message["To"] = message.to
        mime_message["Subject"] = message.subject
        mime_message.set_content(message.body)

        with smtplib.SMTP(self._host, self._port, timeout=SMTP_TIMEOUT_SECONDS) as smtp:
            if self._use_tls:
                smtp.starttls()
            if self._username and self._password:
                smtp.login(self._username, self._password)
            smtp.send_message(mime_message)


class LogEmailSender:
    """Local development only: the e-mail, links included, goes to the API log."""

    def send(self, message: EmailMessage) -> None:
        logger.info(
            "E-mail não enviado (SMTP desligado em ambiente local)\n"
            "Para: %s\nAssunto: %s\n\n%s",
            message.to,
            message.subject,
            message.body,
        )


def build_email_sender(settings: Settings) -> EmailSender:
    if settings.smtp_host:
        if not settings.email_from:
            raise RuntimeError("EMAIL_FROM não está definida.")
        return SmtpEmailSender(
            host=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username,
            password=settings.smtp_password,
            use_tls=settings.smtp_use_tls,
            sender=settings.email_from,
        )
    # Outside local development, logging the e-mail would leak reset links into logs.
    if settings.environment != LOCAL_ENVIRONMENT:
        raise RuntimeError("SMTP_HOST não está definida.")
    return LogEmailSender()


def get_email_sender() -> EmailSender:
    return build_email_sender(get_settings())
