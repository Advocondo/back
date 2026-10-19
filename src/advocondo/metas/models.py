import uuid
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Numeric,
    SmallInteger,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from advocondo.common.models import TimestampsMixin, UuidPrimaryKeyMixin
from advocondo.db import Base

MAX_TARGET_DIGITS = 12
TARGET_DECIMAL_PLACES = 2


class Goal(UuidPrimaryKeyMixin, TimestampsMixin, Base):
    """Meta mensal, em reais de comissão, de um membro da Equipe Operacional (US36)."""

    __tablename__ = "goals"
    __table_args__ = (
        # Uma meta por colaborador e mês.
        UniqueConstraint("user_id", "year", "month"),
        CheckConstraint("month BETWEEN 1 AND 12", name="month_is_valid"),
        CheckConstraint("target_amount > 0", name="target_amount_is_positive"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )
    year: Mapped[int] = mapped_column(SmallInteger)
    month: Mapped[int] = mapped_column(SmallInteger)
    target_amount: Mapped[Decimal] = mapped_column(
        Numeric(MAX_TARGET_DIGITS, TARGET_DECIMAL_PLACES)
    )