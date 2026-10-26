import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from advocondo.common.models import UuidPrimaryKeyMixin
from advocondo.common.storage import StoredFileMixin
from advocondo.db import Base


class CondominiumMonthlyReport(UuidPrimaryKeyMixin, StoredFileMixin, Base):
    __tablename__ = "condominium_monthly_reports"
    __table_args__ = (
        UniqueConstraint(
            "condominium_id",
            "year",
            "month",
            name="uq_condominium_monthly_reports_condominium_id",
        ),
        CheckConstraint("month BETWEEN 1 AND 12", name="month_in_range"),
        CheckConstraint(
            "(content IS NULL) <> (storage_key IS NULL)", name="stored_in_one_place"
        ),
    )

    condominium_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("condominiums.id", ondelete="CASCADE"), index=True
    )
    year: Mapped[int] = mapped_column(Integer)
    month: Mapped[int] = mapped_column(Integer)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    @property
    def file_name(self) -> str:
        return f"relatorio-condominio-{self.year}-{self.month:02}.pdf"
