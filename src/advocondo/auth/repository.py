import uuid
from datetime import datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from advocondo.auth.models import PasswordResetLink, UserSession


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

    def delete(self, user_session: UserSession) -> None:
        self._session.delete(user_session)
        self._session.flush()

    def delete_all_of_user(self, user_id: uuid.UUID) -> None:
        self._session.execute(delete(UserSession).where(UserSession.user_id == user_id))

    def delete_all_of_user_except(self, user_session: UserSession) -> None:
        self._session.execute(
            delete(UserSession).where(
                UserSession.user_id == user_session.user_id,
                UserSession.id != user_session.id,
            )
        )


class PasswordResetLinkRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, link: PasswordResetLink) -> None:
        self._session.add(link)
        self._session.flush()

    def get_by_token_hash(self, token_hash: str) -> PasswordResetLink | None:
        return self._session.scalar(
            select(PasswordResetLink).where(PasswordResetLink.token_hash == token_hash)
        )

    def delete_all_of_user(self, user_id: uuid.UUID) -> None:
        self._session.execute(
            delete(PasswordResetLink).where(PasswordResetLink.user_id == user_id)
        )

    def count_created_after(self, user_id: uuid.UUID, moment: datetime) -> int:
        return (
            self._session.scalar(
                select(func.count())
                .select_from(PasswordResetLink)
                .where(
                    PasswordResetLink.user_id == user_id,
                    PasswordResetLink.created_at > moment,
                )
            )
            or 0
        )

    def expire_all_of_user(self, user_id: uuid.UUID, now: datetime) -> None:
        self._session.execute(
            update(PasswordResetLink)
            .where(
                PasswordResetLink.user_id == user_id,
                PasswordResetLink.expires_at > now,
            )
            .values(expires_at=now)
        )
