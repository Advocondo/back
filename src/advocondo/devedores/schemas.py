import uuid
from typing import Annotated, Self

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from advocondo.common.normalization import keep_only_digits
from advocondo.devedores.models import (
    MAX_EMAIL_LENGTH,
    MAX_NAME_LENGTH,
    MAX_UNIT_LENGTH,
)
from advocondo.devedores.spreadsheet import ImportRowStatus

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


class DebtorUpdateRequest(BaseModel):
    """Only the fields sent are changed; phone or e-mail sent as null is cleared."""

    model_config = ConfigDict(extra="forbid")

    name: DebtorName | None = None
    unit: Unit | None = None
    phone: Phone | None = None
    email: EmailStr | None = Field(default=None, max_length=MAX_EMAIL_LENGTH)

    @field_validator("name", "unit")
    @classmethod
    def _required_field_cannot_be_removed(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("O nome e a unidade não podem ficar vazios.")
        return value

    @model_validator(mode="after")
    def _has_a_change(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("Informe ao menos um campo para alterar.")
        return self


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


class DebtorImportRowResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    number: int = Field(description="Número da linha no Excel")
    status: ImportRowStatus
    values: dict[str, str | None] = Field(description="Texto lido de cada coluna")
    errors: list[str]
    similar_debtors: list[DebtorResponse]
    repeats_row: int | None = Field(
        description="Linha anterior da planilha com o mesmo devedor"
    )


class DebtorImportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    confirmed: bool
    imported: int
    rows: list[DebtorImportRowResponse]
