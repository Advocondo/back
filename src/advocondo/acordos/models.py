import enum
import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from advocondo.common.models import TimestampsMixin, UuidPrimaryKeyMixin, string_enum
from advocondo.condominios.models import Condominium
from advocondo.db import Base
from advocondo.devedores.models import Debtor

if TYPE_CHECKING:
    from advocondo.parcelas.models import Installment

# Money is stored as NUMERIC with cents, never as float.
MONEY = Numeric(12, 2)
PERCENTAGE = Numeric(5, 2)


class AgreementStatus(enum.StrEnum):
    ACTIVE = "active"


class Agreement(UuidPrimaryKeyMixin, TimestampsMixin, Base):
    """An out-of-court payment agreement with a debtor (US15)."""

    __tablename__ = "agreements"
    __table_args__ = (
        CheckConstraint("total_amount > 0", name="total_amount_is_positive"),
        CheckConstraint(
            "fee_amount >= 0 AND fee_amount <= total_amount",
            name="fee_amount_within_total",
        ),
        CheckConstraint(
            "fee_percentage >= 0 AND fee_percentage <= 100",
            name="fee_percentage_within_range",
        ),
    )

    # Required, so no agreement exists without a registered condominium (US12-CA01)
    # and the condominium's Client users can see it (US15-CA03).
    condominium_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("condominiums.id"), index=True
    )
    debtor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("debtors.id"), index=True)
    total_amount: Mapped[Decimal] = mapped_column(MONEY)
    # The office's share of the total (US16). The percentage is kept only when the
    # user typed it, to show it again; the amount is what every calculation uses.
    fee_amount: Mapped[Decimal] = mapped_column(MONEY)
    fee_percentage: Mapped[Decimal | None] = mapped_column(PERCENTAGE)
    status: Mapped[AgreementStatus] = mapped_column(
        string_enum(AgreementStatus, name="agreement_status"),
        default=AgreementStatus.ACTIVE,
    )

    condominium: Mapped[Condominium] = relationship(lazy="joined")
    debtor: Mapped[Debtor] = relationship(lazy="joined")
    installments: Mapped[list["Installment"]] = relationship(
        order_by="Installment.number", cascade="all, delete-orphan"
    )

    @property
    def installment_count(self) -> int:
        return len(self.installments)
