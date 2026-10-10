from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from advocondo.users.models import User


class UserRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_email(self, email: str) -> User | None:
        return self._session.scalar(select(User).where(User.email == email))

    def is_any_registered(self) -> bool:
        return bool(self._session.scalar(select(exists().select_from(User))))

    def add(self, user: User) -> None:
        self._session.add(user)
        self._session.flush()
