import re
from datetime import date, datetime
from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    field_validator,
)

from advocondo.condominios.domain import is_valid_cnpj

_NON_DIGITS = re.compile(r"\D")


def _digits(value: object) -> object:
    """Aceita máscara (14.447.918/0001-98, 12345-678, (61) 91234-5678)."""
    if isinstance(value, str):
        return _NON_DIGITS.sub("", value)
    return value


def _valid_cnpj(cnpj: str) -> str:
    if not is_valid_cnpj(cnpj):
        raise ValueError("CNPJ inválido.")
    return cnpj


Text = Annotated[str, StringConstraints(strip_whitespace=True)]
Cnpj = Annotated[
    str,
    BeforeValidator(_digits),
    StringConstraints(pattern=r"^\d{14}$"),
    AfterValidator(_valid_cnpj),
]
Cep = Annotated[str, BeforeValidator(_digits), StringConstraints(pattern=r"^\d{8}$")]
Telefone = Annotated[
    str, BeforeValidator(_digits), StringConstraints(pattern=r"^\d{10,11}$")
]
Uf = Annotated[
    str,
    BeforeValidator(lambda v: v.strip().upper() if isinstance(v, str) else v),
    StringConstraints(pattern=r"^[A-Z]{2}$"),
]


Nome = Annotated[Text, Field(min_length=1, max_length=200)]


class CondominioFields(BaseModel):
    """Campos comuns, todos opcionais; `nome` é declarado em cada schema."""

    cnpj: Cnpj | None = None

    cep: Cep | None = None
    logradouro: Annotated[Text, Field(min_length=1, max_length=200)] | None = None
    bairro: Annotated[Text, Field(min_length=1, max_length=100)] | None = None
    cidade: Annotated[Text, Field(min_length=1, max_length=100)] | None = None
    uf: Uf | None = None

    sindico_nome: Annotated[Text, Field(min_length=1, max_length=200)] | None = None
    sindico_email: EmailStr | None = None
    sindico_telefone: Telefone | None = None

    contrato_inicio: date | None = None
    contrato_renovacao: date | None = None


class CondominioCreate(CondominioFields):
    nome: Nome


class CondominioUpdate(CondominioFields):
    """PATCH: só os campos enviados mudam; `nome`, se enviado, não pode ser nulo."""

    nome: Nome | None = None

    @field_validator("nome")
    @classmethod
    def _nome_nao_nulo(cls, nome: str | None) -> str:
        if nome is None:
            raise ValueError("O nome não pode ser removido.")
        return nome


class CondominioRead(CondominioFields):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nome: str
    created_at: datetime
    updated_at: datetime
