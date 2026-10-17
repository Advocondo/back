import enum
import uuid
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from advocondo.common.models import TimestampsMixin, UuidPrimaryKeyMixin, string_enum
from advocondo.condominios.models import Condominium
from advocondo.db import Base
from advocondo.devedores.models import Debtor

# Money is stored as NUMERIC with cents, never as float.
MONEY = Numeric(12, 2)


class AgreementStatus(enum.StrEnum):
    ACTIVE = "active"


class Agreement(UuidPrimaryKeyMixin, TimestampsMixin, Base):
    """An out-of-court payment agreement with a debtor (US15)."""

    __tablename__ = "agreements"
    __table_args__ = (
        CheckConstraint("total_amount > 0", name="total_amount_is_positive"),
    )

    # Required, so no agreement exists without a registered condominium (US12-CA01)
    # and the condominium's Client users can see it (US15-CA03).
    condominium_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("condominiums.id"), index=True
    )
    debtor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("debtors.id"), index=True)
    total_amount: Mapped[Decimal] = mapped_column(MONEY)
    status: Mapped[AgreementStatus] = mapped_column(
        string_enum(AgreementStatus, name="agreement_status"),
        default=AgreementStatus.ACTIVE,
    )

    condominium: Mapped[Condominium] = relationship(lazy="joined")
    debtor: Mapped[Debtor] = relationship(lazy="joined")
