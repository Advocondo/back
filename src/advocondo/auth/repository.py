from sqlalchemy import select
from sqlalchemy.orm import Session

from advocondo.auth.models import UserSession


class UserSessionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, user_session: UserSession) -> None:
        self._session.add(user_session)
        self._session.flush()

    def get_by_token_hash(self, token_hash: str) -> UserSession | None:
        return self._session.scalar(
            select(UserSession).where(UserSession.token_hash == token_hash)
        )
