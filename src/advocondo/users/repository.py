import uuid
from collections.abc import Collection, Sequence

from sqlalchemy import delete, exists, select
from sqlalchemy.orm import Session

from advocondo.condominios.models import Condominium
from advocondo.users.models import (
    Role,
    User,
    UserAuditLog,
    UserCondominium,
    UserInvite,
    UserStatus,
)


class UserRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_email(self, email: str) -> User | None:
        return self._session.scalar(select(User).where(User.email == email))

    def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return self._session.get(User, user_id)

    def get_by_id_for_update(self, user_id: uuid.UUID) -> User | None:
        """Loads the user and holds a row lock until the transaction ends."""
        return self._session.scalar(
            select(User).where(User.id == user_id).with_for_update()
        )

    def is_any_registered(self) -> bool:
        return bool(self._session.scalar(select(exists().select_from(User))))

    def list_active_lawyers(self) -> list[User]:
        # Mesma regra de User.can_be_responsible_lawyer, aplicada no banco.
        return list(
            self._session.scalars(
                select(User)
                .where(User.is_lawyer.is_(True), User.status == UserStatus.ACTIVE)
                .order_by(User.name)
            )
        )

    def list_active_admins(self) -> list[User]:
        return list(
            self._session.scalars(
                select(User).where(
                    User.role == Role.ADMIN, User.status == UserStatus.ACTIVE
                )
            )
        )

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


class UserCondominiumRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def condominium_ids_of(self, user_id: uuid.UUID) -> set[uuid.UUID]:
        """The condominiums a Client may see. Empty when none is linked (US10-CA02).

        Listings of Client data (e.g. the agreements panel, US37) filter by this set.
        """
        return set(
            self._session.scalars(
                select(UserCondominium.condominium_id).where(
                    UserCondominium.user_id == user_id
                )
            )
        )

    def list_condominiums_of(self, user_id: uuid.UUID) -> Sequence[Condominium]:
        return self._session.scalars(
            select(Condominium)
            .join(UserCondominium, UserCondominium.condominium_id == Condominium.id)
            .where(UserCondominium.user_id == user_id)
            .order_by(Condominium.name, Condominium.id)
        ).all()

    def existing_condominium_ids(
        self, condominium_ids: Collection[uuid.UUID]
    ) -> set[uuid.UUID]:
        if not condominium_ids:
            return set()
        return set(
            self._session.scalars(
                select(Condominium.id).where(Condominium.id.in_(condominium_ids))
            )
        )

    def clear(self, user_id: uuid.UUID) -> None:
        self._session.execute(
            delete(UserCondominium).where(UserCondominium.user_id == user_id)
        )

    def replace(self, user_id: uuid.UUID, condominium_ids: set[uuid.UUID]) -> None:
        """Makes `condominium_ids` the user's whole set, changing only the difference."""
        current = self.condominium_ids_of(user_id)
        removed = current - condominium_ids
        if removed:
            self._session.execute(
                delete(UserCondominium).where(
                    UserCondominium.user_id == user_id,
                    UserCondominium.condominium_id.in_(removed),
                )
            )
        self._session.add_all(
            UserCondominium(user_id=user_id, condominium_id=condominium_id)
            for condominium_id in condominium_ids - current
        )
        self._session.flush()


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
