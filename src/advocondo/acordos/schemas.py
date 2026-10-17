import uuid
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from advocondo.acordos.models import AgreementStatus

# Up to R$ 9.999.999.999,99, always with cents.
MoneyAmount = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]


class AgreementCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    condominium_id: uuid.UUID
    debtor_id: uuid.UUID
    total_amount: MoneyAmount


class CondominiumSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str


class DebtorSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    unit: str


class AgreementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: AgreementStatus
    total_amount: Decimal
    condominium: CondominiumSummary
    debtor: DebtorSummary
