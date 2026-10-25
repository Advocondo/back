import uuid
from datetime import date, datetime
from typing import Self

from pydantic import BaseModel

from advocondo.acordos.schemas import DebtorSummary, MoneyResponse
from advocondo.notificacoes.models import Notification


class OverdueInstallmentSummary(BaseModel):
    """A parcela atrasada, com o que a central mostra e os ids para abrir a parcela
    ou o acordo ao clicar (US30-CA02)."""

    id: uuid.UUID
    agreement_id: uuid.UUID
    number: int
    installment_count: int
    due_date: date
    remaining_amount: MoneyResponse
    debtor: DebtorSummary


class NotificationResponse(BaseModel):
    id: uuid.UUID
    created_at: datetime
    read_at: datetime | None
    installment: OverdueInstallmentSummary

    @classmethod
    def from_notification(cls, notification: Notification) -> Self:
        installment = notification.installment
        agreement = installment.agreement
        return cls(
            id=notification.id,
            created_at=notification.created_at,
            read_at=notification.read_at,
            installment=OverdueInstallmentSummary(
                id=installment.id,
                agreement_id=agreement.id,
                number=installment.number,
                installment_count=agreement.installment_count,
                due_date=installment.due_date,
                remaining_amount=installment.remaining_amount,
                debtor=DebtorSummary.model_validate(agreement.debtor),
            ),
        )


class NotificationListResponse(BaseModel):
    unread_count: int
    notifications: list[NotificationResponse]
