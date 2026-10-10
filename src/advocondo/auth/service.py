from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.orm import Session

from advocondo.auth.errors import InvalidCredentialsError, InvalidSessionError
from advocondo.auth.models import UserSession
from advocondo.auth.repository import UserSessionRepository
from advocondo.common.clock import Clock
from advocondo.common.passwords import PasswordHasher
from advocondo.common.tokens import generate_opaque_token, hash_token
from advocondo.users.models import User
from advocondo.users.repository import UserRepository


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

    def authenticate(self, token: str) -> User:
        user_session = self._user_sessions.get_by_token_hash(hash_token(token))
        if user_session is None or user_session.is_expired(self._clock.now()):
            raise InvalidSessionError()
        if not user_session.user.can_log_in:
            raise InvalidSessionError()
        return user_session.user

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


def normalize_email(email: str) -> str:
    return email.strip().lower()
