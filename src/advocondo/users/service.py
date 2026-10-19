from dataclasses import dataclass

from sqlalchemy.orm import Session

from advocondo.auth.models import UserSession
from advocondo.auth.repository import UserSessionRepository
from advocondo.common.passwords import MIN_PASSWORD_LENGTH, PasswordHasher
from advocondo.users.errors import (
    CurrentPasswordRequiredError,
    EmailAlreadyInUseError,
    FirstUserAlreadyCreatedError,
    PasswordTooShortError,
    WrongCurrentPasswordError,
)
from advocondo.users.models import Role, User, UserStatus
from advocondo.users.repository import UserRepository


class UserService:
    def __init__(
        self, session: Session, users: UserRepository, password_hasher: PasswordHasher
    ) -> None:
        self._session = session
        self._users = users
        self._password_hasher = password_hasher

    def create_first_admin(self, email: str, name: str, password: str) -> User:
        """Bootstraps the system: invites (US07) need an Administrator to log in."""
        if self._users.is_any_registered():
            raise FirstUserAlreadyCreatedError()
        if len(password) < MIN_PASSWORD_LENGTH:
            raise PasswordTooShortError(MIN_PASSWORD_LENGTH)

        user = User(
            email=normalize_email(email),
            name=name.strip(),
            role=Role.ADMIN,
            status=UserStatus.ACTIVE,
            password_hash=self._password_hasher.hash(password),
        )
        self._users.add(user)
        self._session.commit()
        return user


@dataclass(frozen=True)
class ProfileChanges:
    """Fields left as None are not changed."""

    name: str | None = None
    email: str | None = None
    new_password: str | None = None
    current_password: str | None = None


class ProfileService:
    """The logged-in user editing their own data (US05)."""

    def __init__(
        self,
        session: Session,
        users: UserRepository,
        user_sessions: UserSessionRepository,
        password_hasher: PasswordHasher,
    ) -> None:
        self._session = session
        self._users = users
        self._user_sessions = user_sessions
        self._password_hasher = password_hasher

    def update_profile(
        self, user_session: UserSession, changes: ProfileChanges
    ) -> User:
        user = user_session.user
        new_email = self._new_email(user, changes.email)
        if new_email is not None or changes.new_password is not None:
            # Checked first, so the route cannot be used to find out which e-mails
            # are registered (US05-CA02).
            self._confirm_current_password(user, changes.current_password)
        if new_email is not None and self._users.get_by_email(new_email) is not None:
            raise EmailAlreadyInUseError()

        if changes.name is not None:
            user.name = changes.name.strip()
        if new_email is not None:
            user.email = new_email
        if changes.new_password is not None:
            self._change_password(user_session, changes.new_password)
        self._session.commit()
        return user

    def _new_email(self, user: User, email: str | None) -> str | None:
        """The normalized e-mail, or None when it is missing or the same as now."""
        if email is None:
            return None
        normalized_email = normalize_email(email)
        return None if normalized_email == user.email else normalized_email

    def _confirm_current_password(
        self, user: User, current_password: str | None
    ) -> None:
        if current_password is None:
            raise CurrentPasswordRequiredError()
        if user.password_hash is None or not self._password_hasher.verify(
            user.password_hash, current_password
        ):
            raise WrongCurrentPasswordError()

    def _change_password(self, user_session: UserSession, new_password: str) -> None:
        if len(new_password) < MIN_PASSWORD_LENGTH:
            raise PasswordTooShortError(MIN_PASSWORD_LENGTH)
        user_session.user.password_hash = self._password_hasher.hash(new_password)
        # Like a password reset (US03-CA03), other devices must log in again with
        # the new password; the device that changed it stays logged in.
        self._user_sessions.delete_all_of_user_except(user_session)


def normalize_email(email: str) -> str:
    return email.strip().lower()
