import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from advocondo.common.models import CreatedAtMixin, UuidPrimaryKeyMixin
from advocondo.db import Base
from advocondo.users.models import User

TOKEN_HASH_LENGTH = 64


class UserSession(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    """A logged-in device. Deleting the row ends the session (US03, US06)."""

    __tablename__ = "user_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(TOKEN_HASH_LENGTH), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship()

    def is_expired(self, now: datetime) -> bool:
        return now >= self.expires_at
