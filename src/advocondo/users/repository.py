import uuid

from sqlalchemy import delete, exists, select
from sqlalchemy.orm import Session

from advocondo.users.models import User, UserAuditLog, UserInvite


class UserRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_email(self, email: str) -> User | None:
        return self._session.scalar(select(User).where(User.email == email))

    def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return self._session.get(User, user_id)

    def is_any_registered(self) -> bool:
        return bool(self._session.scalar(select(exists().select_from(User))))

    def add(self, user: User) -> None:
        self._session.add(user)
        self._session.flush()


class UserInviteRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_token_hash(self, token_hash: str) -> UserInvite | None:
        return self._session.scalar(
            select(UserInvite).where(UserInvite.token_hash == token_hash)
        )

    def add(self, invite: UserInvite) -> None:
        self._session.add(invite)
        self._session.flush()

    def delete(self, invite: UserInvite) -> None:
        self._session.delete(invite)

    def delete_all_of_user(self, user_id: uuid.UUID) -> None:
        self._session.execute(delete(UserInvite).where(UserInvite.user_id == user_id))


class UserAuditLogRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, log: UserAuditLog) -> None:
        self._session.add(log)
        self._session.flush()

    def list_by_user(self, user_id: uuid.UUID) -> list[UserAuditLog]:
        return list(
            self._session.scalars(
                select(UserAuditLog)
                .where(UserAuditLog.user_id == user_id)
                .order_by(UserAuditLog.created_at.desc())
            ).all()
        )
