from sqlalchemy.orm import Session

from advocondo.common.passwords import MIN_PASSWORD_LENGTH, PasswordHasher
from advocondo.users.errors import FirstUserAlreadyCreatedError, PasswordTooShortError
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


def normalize_email(email: str) -> str:
    return email.strip().lower()
