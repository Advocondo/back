import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from advocondo.acordos.models import MONEY
from advocondo.common.models import TimestampsMixin, UuidPrimaryKeyMixin
from advocondo.db import Base


class Installment(UuidPrimaryKeyMixin, TimestampsMixin, Base):
    """One monthly invoice of an agreement (US17)."""

    __tablename__ = "installments"
    __table_args__ = (
        UniqueConstraint(
            "agreement_id", "number", name="uq_installments_agreement_id_number"
        ),
        CheckConstraint("amount > 0", name="amount_is_positive"),
        CheckConstraint("number > 0", name="number_is_positive"),
        CheckConstraint(
            "condominium_amount >= 0 AND fee_amount >= 0", name="split_not_negative"
        ),
        CheckConstraint(
            "condominium_amount + fee_amount = amount", name="split_adds_up_to_amount"
        ),
    )

    agreement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agreements.id"), index=True
    )
    # 1 for the first installment, 2 for the second...
    number: Mapped[int]
    due_date: Mapped[date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(MONEY)
    # How the amount is split between the condominium and the office (US16).
    condominium_amount: Mapped[Decimal] = mapped_column(MONEY)
    fee_amount: Mapped[Decimal] = mapped_column(MONEY)
    # Filled when the payment is registered (US26). An installment with a payment
    # date can no longer be edited (US17-CA03).
    payment_date: Mapped[date | None] = mapped_column(Date)

    @property
    def is_paid(self) -> bool:
        return self.payment_date is not None
