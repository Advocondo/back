import uuid
from datetime import date
from typing import Self

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from advocondo.acordos.schemas import MoneyAmount, MoneyResponse
from advocondo.parcelas.models import Installment, InstallmentStatus


class InstallmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agreement_id: uuid.UUID
    number: int
    due_date: date
    amount: MoneyResponse
    condominium_amount: MoneyResponse
    fee_amount: MoneyResponse
    payment_date: date | None
    status: InstallmentStatus

    @classmethod
    def from_installment(cls, installment: Installment, today: date) -> Self:
        return cls(
            id=installment.id,
            agreement_id=installment.agreement_id,
            number=installment.number,
            due_date=installment.due_date,
            amount=installment.amount,
            condominium_amount=installment.condominium_amount,
            fee_amount=installment.fee_amount,
            payment_date=installment.payment_date,
            status=installment.status_on(today),
        )


class InstallmentUpdateRequest(BaseModel):
    """Only the fields sent are changed."""

    model_config = ConfigDict(extra="forbid")

    due_date: date | None = None
    amount: MoneyAmount | None = None

    @field_validator("due_date", "amount")
    @classmethod
    def _cannot_be_removed(cls, value: object) -> object:
        if value is None:
            raise ValueError("O vencimento e o valor não podem ficar vazios.")
        return value

    @model_validator(mode="after")
    def _has_a_change(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("Informe o novo vencimento ou o novo valor.")
        return self
