import re
import uuid
from datetime import date
from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
)

from advocondo.condominios.cnpj import is_valid_cnpj
from advocondo.condominios.models import (
    MAX_ADDRESS_PART_LENGTH,
    MAX_EMAIL_LENGTH,
    MAX_NAME_LENGTH,
)


def keep_only_digits(value: object) -> object:
    """Accepts masked input, such as 14.447.918/0001-98, 12345-678 or (61) 91234-5678."""
    if isinstance(value, str):
        return re.sub(r"\D", "", value)
    return value


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
    BeforeValidator(keep_only_digits),
    StringConstraints(pattern=r"^\d{14}$"),
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


class CondominiumCreateRequest(CondominiumFields):
    name: Name


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
