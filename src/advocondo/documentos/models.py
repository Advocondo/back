import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from advocondo.common.clock import BRAZIL_TIMEZONE
from advocondo.common.models import UuidPrimaryKeyMixin
from advocondo.common.storage import StoredFileMixin
from advocondo.db import Base
from advocondo.users.models import User


class AgreementPdf(UuidPrimaryKeyMixin, StoredFileMixin, Base):
    """Um PDF gerado de um acordo (US24). O arquivo guarda o acordo como estava na
    geração; para ver o estado atual, gera-se outro."""

    __tablename__ = "agreement_pdfs"
    __table_args__ = (
        # Os bytes ficam no banco ou no bucket, nunca nos dois nem em nenhum.
        CheckConstraint(
            "(content IS NULL) <> (storage_key IS NULL)", name="stored_in_one_place"
        ),
    )

    agreement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agreements.id", ondelete="CASCADE"), index=True
    )
    generated_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    # Vem do Clock da aplicação, e não do banco, para ser testável com data fixa.
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    generated_by: Mapped[User] = relationship(lazy="joined")

    @property
    def file_name(self) -> str:
        """Nome sugerido no download, com a data da geração no Brasil."""
        generated_at = self.generated_at.astimezone(BRAZIL_TIMEZONE)
        return f"acordo-{generated_at:%Y%m%d-%H%M%S}.pdf"
