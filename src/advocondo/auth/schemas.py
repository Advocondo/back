import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from advocondo.common.passwords import MAX_PASSWORD_LENGTH
from advocondo.users.models import MAX_EMAIL_LENGTH, Role

# Tokens from generate_opaque_token() have 43 characters; the cap rejects junk early.
MAX_TOKEN_LENGTH = 128


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


class PasswordResetRequest(BaseModel):
    email: str = Field(min_length=1, max_length=MAX_EMAIL_LENGTH)


class PasswordResetRequestResponse(BaseModel):
    detail: str = (
        "Se o e-mail estiver cadastrado, você receberá um link para redefinir a senha."
    )


class PasswordResetConfirmation(BaseModel):
    token: str = Field(min_length=1, max_length=MAX_TOKEN_LENGTH)
    new_password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)
