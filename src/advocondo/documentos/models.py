import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from advocondo.common.clock import BRAZIL_TIMEZONE
from advocondo.common.models import UuidPrimaryKeyMixin
from advocondo.common.storage import StoredFileMixin
from advocondo.db import Base
from advocondo.documentos.rules import MAX_FILENAME_LENGTH, MAX_URL_LENGTH
from advocondo.users.models import User


class DocumentKind(enum.StrEnum):
    FILE = "file"
    LINK = "link"


class AgreementDocumentFile(UuidPrimaryKeyMixin, StoredFileMixin, Base):
    """Os bytes de um documento do tipo arquivo (US21). Ficam no bucket quando ele
    está configurado e, senão, no banco, como os PDFs gerados (common/storage.py).
    Link não tem linha aqui: não há bytes, tipo nem tamanho."""

    __tablename__ = "agreement_document_files"
    __table_args__ = (
        CheckConstraint("size_bytes > 0", name="size_is_positive"),
        # Os bytes ficam no banco ou no bucket, nunca nos dois nem em nenhum.
        CheckConstraint(
            "(content IS NULL) <> (storage_key IS NULL)", name="stored_in_one_place"
        ),
    )


class AgreementDocument(UuidPrimaryKeyMixin, Base):
    """Documento do acordo: um arquivo guardado aqui ou um link para outro lugar (US21).

    Não há exclusão: o vínculo com o acordo é permanente.
    """

    __tablename__ = "agreement_documents"
    __table_args__ = (
        # Ou é um arquivo guardado aqui, ou é um link: nunca os dois e nunca nenhum.
        CheckConstraint("(file_id IS NULL) <> (url IS NULL)", name="file_or_link"),
    )

    # Sem ondelete: o banco recusa apagar um acordo que tenha documentos.
    agreement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agreements.id"), index=True
    )
    filename: Mapped[str] = mapped_column(String(MAX_FILENAME_LENGTH))
    # Os bytes do arquivo; vazio num link.
    file_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agreement_document_files.id"), unique=True
    )
    # Endereço de um documento guardado em outro lugar. O servidor nunca o abre.
    url: Mapped[str | None] = mapped_column(String(MAX_URL_LENGTH))
    uploaded_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    # Vem do Clock da aplicação, e não do banco, para ser testável com data fixa.
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    uploaded_by: Mapped[User] = relationship(
        foreign_keys=[uploaded_by_id], lazy="joined"
    )
    # Só os metadados vêm junto: os bytes (`content`) ficam para o download.
    file: Mapped[AgreementDocumentFile | None] = relationship(lazy="joined")

    @property
    def kind(self) -> DocumentKind:
        return DocumentKind.LINK if self.url is not None else DocumentKind.FILE

    # Tipo e tamanho só existem para arquivos.
    @property
    def content_type(self) -> str | None:
        return self.file.content_type if self.file is not None else None

    @property
    def size(self) -> int | None:
        return self.file.size_bytes if self.file is not None else None


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
