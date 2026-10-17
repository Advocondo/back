import uuid
from typing import Annotated

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
)

from advocondo.common.normalization import keep_only_digits
from advocondo.devedores.models import (
    MAX_EMAIL_LENGTH,
    MAX_NAME_LENGTH,
    MAX_UNIT_LENGTH,
)

DebtorName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_NAME_LENGTH),
]
Unit = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_UNIT_LENGTH),
]
Phone = Annotated[
    str, BeforeValidator(keep_only_digits), StringConstraints(pattern=r"^\d{10,11}$")
]


class DebtorCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    condominium_id: uuid.UUID
    name: DebtorName
    unit: Unit
    phone: Phone | None = None
    email: EmailStr | None = Field(default=None, max_length=MAX_EMAIL_LENGTH)
    # Sent as true after the user saw the similar debtors and still wants to register.
    confirm_duplicate: bool = False


class DebtorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    condominium_id: uuid.UUID
    name: str
    unit: str
    phone: str | None
    email: str | None


class SimilarDebtorsResponse(BaseModel):
    detail: str
    similar_debtors: list[DebtorResponse]
