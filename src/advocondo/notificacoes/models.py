import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from advocondo.common.models import UuidPrimaryKeyMixin, string_enum
from advocondo.db import Base


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
