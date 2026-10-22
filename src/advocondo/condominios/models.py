from datetime import date

from sqlalchemy import CheckConstraint, Date, String
from sqlalchemy.orm import Mapped, mapped_column

from advocondo.common.models import TimestampsMixin, UuidPrimaryKeyMixin
from advocondo.condominios import renewal
from advocondo.db import Base

MAX_NAME_LENGTH = 200
MAX_ADDRESS_PART_LENGTH = 200
MAX_EMAIL_LENGTH = 254
CNPJ_LENGTH = 14
ZIP_CODE_LENGTH = 8
STATE_LENGTH = 2
MAX_PHONE_LENGTH = 11


class Condominium(UuidPrimaryKeyMixin, TimestampsMixin, Base):
    """A condominium the office represents (US12)."""

    __tablename__ = "condominiums"
    __table_args__ = (
        CheckConstraint(
            "contract_renewal_date >= contract_start_date",
            name="renewal_not_before_start",
        ),
    )

    name: Mapped[str] = mapped_column(String(MAX_NAME_LENGTH))
    # Digits only. Unique when given; PostgreSQL allows several NULLs.
    cnpj: Mapped[str | None] = mapped_column(String(CNPJ_LENGTH), unique=True)

    zip_code: Mapped[str | None] = mapped_column(String(ZIP_CODE_LENGTH))
    street: Mapped[str | None] = mapped_column(String(MAX_ADDRESS_PART_LENGTH))
    neighborhood: Mapped[str | None] = mapped_column(String(MAX_ADDRESS_PART_LENGTH))
    city: Mapped[str | None] = mapped_column(String(MAX_ADDRESS_PART_LENGTH))
    state: Mapped[str | None] = mapped_column(String(STATE_LENGTH))

    # The building manager (síndico) or the management company.
    manager_name: Mapped[str | None] = mapped_column(String(MAX_NAME_LENGTH))
    manager_email: Mapped[str | None] = mapped_column(String(MAX_EMAIL_LENGTH))
    manager_phone: Mapped[str | None] = mapped_column(String(MAX_PHONE_LENGTH))

    # Service contract with the office; the renewal is followed in US23.
    contract_start_date: Mapped[date | None] = mapped_column(Date)
    contract_renewal_date: Mapped[date | None] = mapped_column(Date)

    def is_near_renewal(self, today: date) -> bool:
        """Sem data de renovação cadastrada, não há o que sinalizar."""
        if self.contract_renewal_date is None:
            return False

        return renewal.is_near_renewal(self.contract_renewal_date, today)
