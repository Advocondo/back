import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    field_validator,
    model_validator,
)

from advocondo.acordos.models import MAX_CANCELLATION_REASON_LENGTH, AgreementStatus
from advocondo.users.schemas import LawyerResponse

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


class AgreementCancelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Annotated[str | None, Field(max_length=MAX_CANCELLATION_REASON_LENGTH)] = (
        None
    )
    # Obrigatório como `true` para cancelar um acordo que ainda tem parcelas sem
    # pagamento (US20): o aviso é imposto pela API, e não só pela tela.
    confirm_open_installments: bool = False

    @field_validator("reason")
    @classmethod
    def _blank_reason_is_no_reason(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None


class CondominiumSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str


class DebtorSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    unit: str


class UserSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str


class LawyerAssignmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lawyer_id: uuid.UUID


class LawyerAssignmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    previous_lawyer: LawyerResponse | None
    new_lawyer: LawyerResponse
    assigned_by: UserSummary
    assigned_at: datetime


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
    responsible_lawyer: LawyerResponse | None
    cancelled_at: datetime | None
    cancellation_reason: str | None
