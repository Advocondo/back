import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import urlencode

from sqlalchemy.orm import Session

from advocondo.auth.errors import (
    InvalidCredentialsError,
    InvalidPasswordResetLinkError,
    InvalidSessionError,
)
from advocondo.auth.models import PasswordResetLink, UserSession
from advocondo.auth.repository import PasswordResetLinkRepository, UserSessionRepository
from advocondo.common.clock import Clock
from advocondo.common.email import EmailMessage, EmailSender
from advocondo.common.passwords import MIN_PASSWORD_LENGTH, PasswordHasher
from advocondo.common.tokens import generate_opaque_token, hash_token
from advocondo.users.errors import PasswordTooShortError
from advocondo.users.models import User
from advocondo.users.repository import UserRepository
from advocondo.users.service import normalize_email

logger = logging.getLogger(__name__)

# Front-end page that reads the token from the link and asks for the new password.
PASSWORD_RESET_PAGE = "/redefinir-senha"


@dataclass(frozen=True)
class SessionDurations:
    default: timedelta
    remembered: timedelta


@dataclass(frozen=True)
class LoginResult:
    token: str
    user_session: UserSession


class AuthService:
    def __init__(
        self,
        session: Session,
        users: UserRepository,
        user_sessions: UserSessionRepository,
        password_hasher: PasswordHasher,
        clock: Clock,
        session_durations: SessionDurations,
    ) -> None:
        self._session = session
        self._users = users
        self._user_sessions = user_sessions
        self._password_hasher = password_hasher
        self._clock = clock
        self._session_durations = session_durations

    def log_in(self, email: str, password: str, *, remember_me: bool) -> LoginResult:
        user = self._find_user_by_credentials(email, password)
        if not user.can_log_in:
            raise InvalidCredentialsError()

        token = generate_opaque_token()
        user_session = UserSession(
            user=user,
            token_hash=hash_token(token),
            expires_at=self._clock.now() + self._session_duration(remember_me),
        )
        self._user_sessions.add(user_session)
        self._session.commit()
        return LoginResult(token=token, user_session=user_session)

    def authenticate(self, token: str) -> UserSession:
        user_session = self._user_sessions.get_by_token_hash(hash_token(token))
        if user_session is None or user_session.is_expired(self._clock.now()):
            raise InvalidSessionError()
        if not user_session.user.can_log_in:
            raise InvalidSessionError()
        return user_session

    def log_out(self, user_session: UserSession) -> None:
        self._user_sessions.delete(user_session)
        self._session.commit()

    def _find_user_by_credentials(self, email: str, password: str) -> User:
        user = self._users.get_by_email(normalize_email(email))
        if user is None or user.password_hash is None:
            self._password_hasher.simulate_verify(password)
            raise InvalidCredentialsError()
        if not self._password_hasher.verify(user.password_hash, password):
            raise InvalidCredentialsError()
        return user

    def _session_duration(self, remember_me: bool) -> timedelta:
        if remember_me:
            return self._session_durations.remembered
        return self._session_durations.default


@dataclass(frozen=True)
class PasswordResetSettings:
    link_duration: timedelta
    frontend_url: str
    max_requests: int
    request_window: timedelta


class PasswordResetService:
    def __init__(
        self,
        session: Session,
        users: UserRepository,
        reset_links: PasswordResetLinkRepository,
        user_sessions: UserSessionRepository,
        password_hasher: PasswordHasher,
        email_sender: EmailSender,
        clock: Clock,
        settings: PasswordResetSettings,
    ) -> None:
        self._session = session
        self._users = users
        self._reset_links = reset_links
        self._user_sessions = user_sessions
        self._password_hasher = password_hasher
        self._email_sender = email_sender
        self._clock = clock
        self._settings = settings

    def request_reset(self, email: str) -> None:
        """Does nothing for unknown or inactive users, so the caller cannot tell them
        apart from registered ones."""
        user = self._users.get_by_email(normalize_email(email))
        if user is None or not user.can_log_in:
            return
        now = self._clock.now()
        if self._has_reached_request_limit(user, now):
            logger.warning("Limite de pedidos de redefinição de senha atingido")
            return

        self._reset_links.expire_all_of_user(user.id, now)
        token = generate_opaque_token()
        self._reset_links.add(
            PasswordResetLink(
                user=user,
                token_hash=hash_token(token),
                created_at=now,
                expires_at=now + self._settings.link_duration,
            )
        )
        self._session.commit()
        self._send_reset_email(user, token)

    def reset_password(self, token: str, new_password: str) -> None:
        link = self._reset_links.get_by_token_hash(hash_token(token))
        if link is None or link.is_expired(self._clock.now()):
            raise InvalidPasswordResetLinkError()
        if not link.user.can_log_in:
            raise InvalidPasswordResetLinkError()
        if len(new_password) < MIN_PASSWORD_LENGTH:
            raise PasswordTooShortError(MIN_PASSWORD_LENGTH)

        user = link.user
        user.password_hash = self._password_hasher.hash(new_password)
        self._reset_links.delete_all_of_user(user.id)
        self._user_sessions.delete_all_of_user(user.id)
        self._session.commit()

    def _has_reached_request_limit(self, user: User, now: datetime) -> bool:
        """Stops someone from flooding a mailbox with reset e-mails."""
        requests_in_window = self._reset_links.count_created_after(
            user.id, now - self._settings.request_window
        )
        return requests_in_window >= self._settings.max_requests

    def _send_reset_email(self, user: User, token: str) -> None:
        message = build_password_reset_email(
            user, self._reset_url(token), self._settings.link_duration
        )
        try:
            self._email_sender.send(message)
        except Exception:
            # The answer must not change when delivery fails, or it would reveal
            # that the e-mail is registered. The failure goes to the logs and Sentry.
            logger.exception("Falha ao enviar o e-mail de redefinição de senha")

    def _reset_url(self, token: str) -> str:
        base_url = self._settings.frontend_url.rstrip("/")
        return f"{base_url}{PASSWORD_RESET_PAGE}?{urlencode({'token': token})}"


def build_password_reset_email(
    user: User, reset_url: str, link_duration: timedelta
) -> EmailMessage:
    minutes = int(link_duration.total_seconds() // 60)
    body = (
        f"Olá, {user.name}.\n\n"
        "Recebemos um pedido para redefinir a senha da sua conta no Advocondo. "
        f"Para criar uma nova senha, acesse o link abaixo em até {minutes} minutos:\n\n"
        f"{reset_url}\n\n"
        "Se você não fez esse pedido, ignore este e-mail: sua senha continua a mesma.\n"
    )
    return EmailMessage(to=user.email, subject="Redefinição de senha", body=body)
