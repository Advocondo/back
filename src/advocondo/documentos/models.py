import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from advocondo.common.clock import BRAZIL_TIMEZONE
from advocondo.common.models import UuidPrimaryKeyMixin
from advocondo.common.storage import StoredFileMixin
from advocondo.db import Base
from advocondo.documentos.rules import MAX_FILENAME_LENGTH, MAX_URL_LENGTH
from advocondo.users.models import User

CONTENT_TYPE_MAX_LENGTH = 50


class DocumentKind(enum.StrEnum):
    FILE = "file"
    LINK = "link"


class AgreementDocument(UuidPrimaryKeyMixin, Base):
    """Documento do acordo: um arquivo guardado aqui ou um link para outro lugar (US21).

    Não há exclusão: o vínculo com o acordo é permanente.
    """

    __tablename__ = "agreement_documents"
    __table_args__ = (
        CheckConstraint("size > 0", name="size_is_positive"),
        # Ou é um arquivo guardado aqui, ou é um link: nunca os dois e nunca nenhum.
        CheckConstraint("(content IS NULL) <> (url IS NULL)", name="file_or_link"),
    )

    # Sem ondelete: o banco recusa apagar um acordo que tenha documentos.
    agreement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agreements.id"), index=True
    )
    filename: Mapped[str] = mapped_column(String(MAX_FILENAME_LENGTH))
    # Tipo e tamanho só existem para arquivos.
    content_type: Mapped[str | None] = mapped_column(String(CONTENT_TYPE_MAX_LENGTH))
    size: Mapped[int | None]
    # Só é lido no download: a listagem não carrega o arquivo.
    content: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)
    # Endereço de um documento guardado em outro lugar. O servidor nunca o abre.
    url: Mapped[str | None] = mapped_column(String(MAX_URL_LENGTH))
    uploaded_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    # Vem do Clock da aplicação, e não do banco, para ser testável com data fixa.
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    uploaded_by: Mapped[User] = relationship(
        foreign_keys=[uploaded_by_id], lazy="joined"
    )

    @property
    def kind(self) -> DocumentKind:
        return DocumentKind.LINK if self.url is not None else DocumentKind.FILE


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
