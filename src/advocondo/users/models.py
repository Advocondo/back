import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from advocondo.common.models import (
    CreatedAtMixin,
    TimestampsMixin,
    UuidPrimaryKeyMixin,
    string_enum,
)
from advocondo.db import Base

MAX_EMAIL_LENGTH = 254
MAX_NAME_LENGTH = 200
MIN_OAB_LENGTH = 8
MAX_OAB_LENGTH = 12
TOKEN_HASH_LENGTH = 64


class Role(enum.StrEnum):
    ADMIN = "admin"
    OPERATOR = "operator"
    CLIENT = "client"


class UserStatus(enum.StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    INACTIVE = "inactive"


class AuditAction(enum.StrEnum):
    INVITED = "invited"
    STATUS_CHANGED = "status_changed"
    ROLE_CHANGED = "role_changed"
    CONDOMINIUMS_CHANGED = "condominiums_changed"


class User(UuidPrimaryKeyMixin, TimestampsMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("email = lower(email)", name="email_is_lowercase"),
        CheckConstraint(
            "status <> 'active' OR password_hash IS NOT NULL",
            name="active_user_has_password",
        ),
        CheckConstraint(
            "(NOT is_lawyer AND oab_number IS NULL) "
            "OR (is_lawyer AND oab_number IS NOT NULL "
            "AND char_length(oab_number) BETWEEN 8 AND 12)",
            name="lawyer_has_valid_oab_number",
        ),
    )

    email: Mapped[str] = mapped_column(String(MAX_EMAIL_LENGTH), unique=True)
    name: Mapped[str] = mapped_column(String(MAX_NAME_LENGTH))
    role: Mapped[Role] = mapped_column(string_enum(Role, name="role"))
    status: Mapped[UserStatus] = mapped_column(
        string_enum(UserStatus, name="user_status"), default=UserStatus.PENDING
    )
    password_hash: Mapped[str | None] = mapped_column(String(255))
    is_lawyer: Mapped[bool] = mapped_column(Boolean, default=False)
    oab_number: Mapped[str | None] = mapped_column(String(MAX_OAB_LENGTH))

    @property
    def can_log_in(self) -> bool:
        return self.status == UserStatus.ACTIVE

    @property
    def can_be_responsible_lawyer(self) -> bool:
        """Só advogado ativo pode responder por um acordo (US18)."""
        return self.is_lawyer and self.status == UserStatus.ACTIVE


class UserInvite(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    """A pending invitation (US07). One per user: the invited user starts as PENDING
    and becomes ACTIVE when they accept, which deletes this row."""

    __tablename__ = "user_invites"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )
    invited_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(TOKEN_HASH_LENGTH), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(foreign_keys=[user_id])
    invited_by: Mapped[User | None] = relationship(foreign_keys=[invited_by_id])

    def is_expired(self, now: datetime) -> bool:
        return now >= self.expires_at


class UserCondominium(CreatedAtMixin, Base):
    """Links a Client user to a condominium they follow (US10). A Client sees only
    the data of the condominiums linked to them; with no link they see nothing."""

    __tablename__ = "user_condominiums"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    condominium_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("condominiums.id", ondelete="CASCADE"), primary_key=True, index=True
    )


class UserAuditLog(UuidPrimaryKeyMixin, Base):
    """Registro de ações de gestão de usuários (US11)."""

    __tablename__ = "user_audit_logs"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    action: Mapped[AuditAction] = mapped_column(
        string_enum(AuditAction, name="audit_action")
    )
    old_value: Mapped[str | None] = mapped_column(String(255))
    new_value: Mapped[str | None] = mapped_column(String(255))
    # Só em CONDOMINIUMS_CHANGED: {"added": [...], "removed": [...]}, cada item com
    # o id e o nome do condomínio na data da ação. Nas demais ações fica vazio.
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # clock_timestamp() em vez de now() (do CreatedAtMixin): now() retorna o
    # início da transação no PostgreSQL, então várias ações na mesma transação
    # compartilhariam o timestamp e perderiam a ordem.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )

    user: Mapped[User] = relationship(foreign_keys=[user_id])
    actor: Mapped[User | None] = relationship(foreign_keys=[actor_id])

    @property
    def added_condominiums(self) -> list[dict[str, str]]:
        return list((self.details or {}).get("added", []))

    @property
    def removed_condominiums(self) -> list[dict[str, str]]:
        return list((self.details or {}).get("removed", []))
