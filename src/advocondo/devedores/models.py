import uuid

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from advocondo.common.models import TimestampsMixin, UuidPrimaryKeyMixin
from advocondo.db import Base

MAX_NAME_LENGTH = 200
MAX_UNIT_LENGTH = 50
MAX_EMAIL_LENGTH = 254
MAX_PHONE_LENGTH = 11


class Debtor(UuidPrimaryKeyMixin, TimestampsMixin, Base):
    """A resident in default, registered once and reused in every agreement (US13)."""

    __tablename__ = "debtors"
    __table_args__ = (
        CheckConstraint("phone IS NOT NULL OR email IS NOT NULL", name="has_a_contact"),
    )

    condominium_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("condominiums.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(MAX_NAME_LENGTH))
    # Free text, as each condominium names its units differently ("Bloco B 304").
    unit: Mapped[str] = mapped_column(String(MAX_UNIT_LENGTH))
    phone: Mapped[str | None] = mapped_column(String(MAX_PHONE_LENGTH))
    email: Mapped[str | None] = mapped_column(String(MAX_EMAIL_LENGTH))
