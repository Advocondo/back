import uuid
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints

from advocondo.common.passwords import MAX_PASSWORD_LENGTH
from advocondo.users.models import MAX_EMAIL_LENGTH, MAX_NAME_LENGTH, Role


class FirstAdminRequest(BaseModel):
    email: EmailStr = Field(max_length=MAX_EMAIL_LENGTH)
    name: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=1, max_length=MAX_NAME_LENGTH
        ),
    ]
    password: str = Field(max_length=MAX_PASSWORD_LENGTH)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: str
    role: Role
