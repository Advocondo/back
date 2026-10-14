import uuid
from typing import Annotated, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    model_validator,
)

from advocondo.common.passwords import MAX_PASSWORD_LENGTH
from advocondo.users.models import MAX_EMAIL_LENGTH, MAX_NAME_LENGTH, Role

UserName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_NAME_LENGTH),
]


class FirstAdminRequest(BaseModel):
    email: EmailStr = Field(max_length=MAX_EMAIL_LENGTH)
    name: UserName
    password: str = Field(max_length=MAX_PASSWORD_LENGTH)


class ProfileUpdateRequest(BaseModel):
    """Only the fields sent are changed."""

    name: UserName | None = None
    email: EmailStr | None = Field(default=None, max_length=MAX_EMAIL_LENGTH)
    new_password: str | None = Field(default=None, max_length=MAX_PASSWORD_LENGTH)
    current_password: str | None = Field(default=None, max_length=MAX_PASSWORD_LENGTH)

    @model_validator(mode="after")
    def _has_a_change(self) -> Self:
        if self.name is None and self.email is None and self.new_password is None:
            raise ValueError("Informe o nome, o e-mail ou a nova senha.")
        return self


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: str
    role: Role
