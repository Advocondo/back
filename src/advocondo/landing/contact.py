import logging

from advocondo.common.email import EmailMessage, EmailSender
from advocondo.landing.captcha import CaptchaVerifier
from advocondo.landing.errors import ContactFormUnavailableError, InvalidCaptchaError
from advocondo.landing.schemas import ContactMessageRequest
from advocondo.landing.service import LandingService

logger = logging.getLogger(__name__)


class ContactService:
    """Forwards the contact form by e-mail. Nothing is stored: the inbox is the record."""

    def __init__(
        self,
        landing: LandingService,
        captcha: CaptchaVerifier,
        email_sender: EmailSender,
    ) -> None:
        self._landing = landing
        self._captcha = captcha
        self._email_sender = email_sender

    def send(self, request: ContactMessageRequest) -> None:
        # The same answer as a real send, so the bot does not learn it was caught.
        if request.website:
            return
        if not self._captcha.is_valid(request.captcha_token):
            raise InvalidCaptchaError()
        recipient = self._landing.get_content().contact.email
        if recipient is None:
            logger.error(
                "A landing não tem e-mail de contato para receber o formulário"
            )
            raise ContactFormUnavailableError()
        try:
            self._email_sender.send(build_contact_email(request, recipient))
        except Exception as error:
            logger.exception("Falha ao enviar o e-mail do formulário de contato")
            raise ContactFormUnavailableError() from error


def build_contact_email(request: ContactMessageRequest, recipient: str) -> EmailMessage:
    body = (
        "Nova mensagem pelo formulário de contato do site.\n\n"
        f"Nome: {request.name}\n"
        f"Telefone: {request.phone}\n"
        f"E-mail: {request.email}\n\n"
        f"Mensagem:\n{request.message or '(sem mensagem)'}\n"
    )
    return EmailMessage(
        to=recipient,
        subject="Novo contato pelo site",
        body=body,
        reply_to=request.email,
    )
