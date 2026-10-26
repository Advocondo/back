import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from advocondo.common.models import UuidPrimaryKeyMixin, string_enum
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


class ClientNotificationEvent(enum.StrEnum):
    AGREEMENT_CREATED = "agreement_created"
    AGREEMENT_UPDATED = "agreement_updated"
    AGREEMENT_CANCELLED = "agreement_cancelled"
    PAYMENT_UPDATED = "payment_updated"
    CONDOMINIUM_UPDATED = "condominium_updated"
    MONTHLY_REPORT_READY = "monthly_report_ready"


class ClientNotificationLog(UuidPrimaryKeyMixin, Base):
    """One successful automatic e-mail to one linked Client (US40-CA03)."""

    __tablename__ = "client_notification_logs"
    __table_args__ = (
        Index("ix_client_notification_logs_user_id", "user_id"),
        Index("ix_client_notification_logs_condominium_id", "condominium_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )
    condominium_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("condominiums.id", ondelete="CASCADE")
    )
    event_type: Mapped[ClientNotificationEvent] = mapped_column(
        string_enum(ClientNotificationEvent, name="client_notification_event")
    )
    message: Mapped[str] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String(1000))
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
