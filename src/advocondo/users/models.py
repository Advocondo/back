import enum

from sqlalchemy import CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from advocondo.common.models import TimestampsMixin, UuidPrimaryKeyMixin, string_enum
from advocondo.db import Base

MAX_EMAIL_LENGTH = 254
MAX_NAME_LENGTH = 200


class Role(enum.StrEnum):
    ADMIN = "admin"
    OPERATOR = "operator"
    CLIENT = "client"


class UserStatus(enum.StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    INACTIVE = "inactive"


class User(UuidPrimaryKeyMixin, TimestampsMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("email = lower(email)", name="email_is_lowercase"),
        CheckConstraint(
            "status <> 'active' OR password_hash IS NOT NULL",
            name="active_user_has_password",
        ),
    )

    email: Mapped[str] = mapped_column(String(MAX_EMAIL_LENGTH), unique=True)
    name: Mapped[str] = mapped_column(String(MAX_NAME_LENGTH))
    role: Mapped[Role] = mapped_column(string_enum(Role, name="role"))
    status: Mapped[UserStatus] = mapped_column(
        string_enum(UserStatus, name="user_status"), default=UserStatus.PENDING
    )
    password_hash: Mapped[str | None] = mapped_column(String(255))

    @property
    def can_log_in(self) -> bool:
        return self.status == UserStatus.ACTIVE
