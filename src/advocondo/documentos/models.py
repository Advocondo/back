import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from advocondo.common.clock import BRAZIL_TIMEZONE
from advocondo.common.models import UuidPrimaryKeyMixin
from advocondo.common.storage import StoredFileMixin
from advocondo.db import Base
from advocondo.documentos.rules import MAX_FILENAME_LENGTH
from advocondo.users.models import User

CONTENT_TYPE_MAX_LENGTH = 50


class AgreementDocument(UuidPrimaryKeyMixin, Base):
    """Documento anexado a um acordo. Não há exclusão: o vínculo é permanente (US21)."""

    __tablename__ = "agreement_documents"
    __table_args__ = (CheckConstraint("size > 0", name="size_is_positive"),)

    # Sem ondelete: o banco recusa apagar um acordo que tenha documentos.
    agreement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agreements.id"), index=True
    )
    filename: Mapped[str] = mapped_column(String(MAX_FILENAME_LENGTH))
    content_type: Mapped[str] = mapped_column(String(CONTENT_TYPE_MAX_LENGTH))
    size: Mapped[int]
    # Só é lido no download: a listagem não carrega o arquivo.
    content: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    uploaded_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    # Vem do Clock da aplicação, e não do banco, para ser testável com data fixa.
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    uploaded_by: Mapped[User] = relationship(
        foreign_keys=[uploaded_by_id], lazy="joined"
    )


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
