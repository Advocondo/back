import uuid
from datetime import date
from typing import Annotated, Self

from pydantic import (
    AfterValidator,
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
from advocondo.condominios.cnpj import is_valid_cnpj, normalize_cnpj
from advocondo.condominios.models import (
    MAX_ADDRESS_PART_LENGTH,
    MAX_EMAIL_LENGTH,
    MAX_NAME_LENGTH,
    Condominium,
)


def uppercase(value: object) -> object:
    return value.strip().upper() if isinstance(value, str) else value


def check_cnpj_digits(cnpj: str) -> str:
    if not is_valid_cnpj(cnpj):
        raise ValueError("CNPJ inválido.")
    return cnpj


Name = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_NAME_LENGTH),
]
AddressPart = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=MAX_ADDRESS_PART_LENGTH
    ),
]
Cnpj = Annotated[
    str,
    BeforeValidator(normalize_cnpj),
    StringConstraints(pattern=r"^[0-9A-Z]{12}\d{2}$"),
    AfterValidator(check_cnpj_digits),
]
ZipCode = Annotated[
    str, BeforeValidator(keep_only_digits), StringConstraints(pattern=r"^\d{8}$")
]
State = Annotated[
    str, BeforeValidator(uppercase), StringConstraints(pattern=r"^[A-Z]{2}$")
]
Phone = Annotated[
    str, BeforeValidator(keep_only_digits), StringConstraints(pattern=r"^\d{10,11}$")
]


class CondominiumFields(BaseModel):
    """Optional fields shared by registration and editing."""

    model_config = ConfigDict(extra="forbid")

    cnpj: Cnpj | None = None
    zip_code: ZipCode | None = None
    street: AddressPart | None = None
    neighborhood: AddressPart | None = None
    city: AddressPart | None = None
    state: State | None = None
    manager_name: Name | None = None
    manager_email: EmailStr | None = Field(default=None, max_length=MAX_EMAIL_LENGTH)
    manager_phone: Phone | None = None
    contract_start_date: date | None = None
    contract_renewal_date: date | None = None
    # Preenchido por from_condominium, que sabe qual é a data de hoje.
    near_renewal: bool = False


class CondominiumCreateRequest(CondominiumFields):
    name: Name


class CondominiumUpdateRequest(CondominiumFields):
    """Only the fields sent are changed; an optional field sent as null is cleared."""

    name: Name | None = None

    @field_validator("name")
    @classmethod
    def _name_cannot_be_removed(cls, name: str | None) -> str:
        if name is None:
            raise ValueError("O nome do condomínio não pode ficar vazio.")
        return name

    @model_validator(mode="after")
    def _has_a_change(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("Informe ao menos um campo para alterar.")
        return self


class CondominiumResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    cnpj: str | None
    zip_code: str | None
    street: str | None
    neighborhood: str | None
    city: str | None
    state: str | None
    manager_name: str | None
    manager_email: str | None
    manager_phone: str | None
    contract_start_date: date | None
    contract_renewal_date: date | None

    @classmethod
    def from_condominium(cls, condominium: Condominium, today: date) -> Self:
        return cls.model_validate(condominium).model_copy(
            update={"near_renewal": condominium.is_near_renewal(today)}
        )
