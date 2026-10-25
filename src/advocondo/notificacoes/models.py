import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from advocondo.common.models import UuidPrimaryKeyMixin
from advocondo.db import Base
from advocondo.parcelas.models import Installment


class Notification(UuidPrimaryKeyMixin, Base):
    """Aviso, no sino de um usuário, de que uma parcela ficou atrasada (US30)."""

    __tablename__ = "notifications"
    # Um aviso por parcela e usuário: o comando diário pode rodar de novo sem repetir.
    __table_args__ = (
        UniqueConstraint(
            "user_id", "installment_id", name="uq_notifications_user_id_installment_id"
        ),
    )

    # A regra única acima já indexa user_id, pela listagem de cada usuário; o índice
    # em installment_id serve ao comando diário, que procura pela parcela.
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )
    installment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("installments.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    installment: Mapped[Installment] = relationship()

    @property
    def is_read(self) -> bool:
        return self.read_at is not None

    def mark_as_read(self, now: datetime) -> None:
        """Marca como lida; uma notificação já lida mantém a data da primeira leitura."""
        if self.read_at is None:
            self.read_at = now
