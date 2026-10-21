import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, model_validator

from advocondo.acordos.models import AgreementStatus

MAX_INSTALLMENTS = 120

# Up to R$ 9.999.999.999,99, always with cents.
MoneyAmount = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
FeeAmount = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]
FeePercentage = Annotated[Decimal, Field(ge=0, le=100, max_digits=5, decimal_places=2)]


def two_decimal_places(value: Decimal) -> str:
    """Money always leaves the API as "100.00", even when typed as "100"."""
    return f"{value:.2f}"


MoneyResponse = Annotated[Decimal, PlainSerializer(two_decimal_places, return_type=str)]
PercentageResponse = Annotated[
    Decimal, PlainSerializer(two_decimal_places, return_type=str)
]


class AgreementCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    condominium_id: uuid.UUID
    debtor_id: uuid.UUID
    total_amount: MoneyAmount
    # The installments are generated with the agreement (US17-CA01).
    installment_count: Annotated[int, Field(ge=1, le=MAX_INSTALLMENTS)]
    first_due_date: date
    # The fee is given either as a percentage of the total or in reais (US16-CA01).
    fee_percentage: FeePercentage | None = None
    fee_amount: FeeAmount | None = None

    @model_validator(mode="after")
    def _fee_given_one_way(self) -> Self:
        if (self.fee_percentage is None) == (self.fee_amount is None):
            raise ValueError(
                "Informe os honorários em percentual ou em valor, não os dois."
            )
        return self


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
    total_amount: MoneyResponse
    fee_amount: MoneyResponse
    fee_percentage: PercentageResponse | None
    installment_count: int
    condominium: CondominiumSummary
    debtor: DebtorSummary
