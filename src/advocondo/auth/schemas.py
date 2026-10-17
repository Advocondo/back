import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from advocondo.common.passwords import MAX_PASSWORD_LENGTH
from advocondo.users.models import MAX_EMAIL_LENGTH, Role


class LoginRequest(BaseModel):
    email: str = Field(min_length=1, max_length=MAX_EMAIL_LENGTH)
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)
    remember_me: bool = False


class AuthenticatedUser(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: str
    role: Role


class LoginResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime
    user: AuthenticatedUser
