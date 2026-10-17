import uuid
from typing import Annotated, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from advocondo.common.passwords import MAX_PASSWORD_LENGTH
from advocondo.users.models import (
    MAX_EMAIL_LENGTH,
    MAX_NAME_LENGTH,
    MAX_OAB_LENGTH,
    MIN_OAB_LENGTH,
    Role,
    UserStatus,
)

MAX_TOKEN_LENGTH = 128

UserName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_NAME_LENGTH),
]


class FirstAdminRequest(BaseModel):
    email: EmailStr = Field(max_length=MAX_EMAIL_LENGTH)
    name: UserName
    password: str = Field(max_length=MAX_PASSWORD_LENGTH)


class ProfileUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: UserName | None = None
    email: EmailStr | None = Field(default=None, max_length=MAX_EMAIL_LENGTH)
    new_password: str | None = Field(default=None, max_length=MAX_PASSWORD_LENGTH)
    current_password: str | None = Field(default=None, max_length=MAX_PASSWORD_LENGTH)

    @model_validator(mode="after")
    def _has_a_change(self) -> Self:
        if self.name is None and self.email is None and self.new_password is None:
            raise ValueError("Informe o nome, o e-mail ou a nova senha.")
        return self


class InviteUserRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr = Field(max_length=MAX_EMAIL_LENGTH)
    name: UserName
    role: Role
    is_lawyer: bool = False
    oab_number: str | None = Field(
        default=None, min_length=MIN_OAB_LENGTH, max_length=MAX_OAB_LENGTH
    )

    @field_validator("oab_number", mode="before")
    @classmethod
    def _blank_as_none(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value


class AcceptInviteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1, max_length=MAX_TOKEN_LENGTH)
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: str
    role: Role
    status: UserStatus
    is_lawyer: bool
    oab_number: str | None


class UserStatusUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: UserStatus

    @field_validator("status")
    @classmethod
    def _only_active_or_inactive(cls, value: UserStatus) -> UserStatus:
        if value == UserStatus.PENDING:
            raise ValueError("Use o convite para criar um usuário pendente.")
        return value
