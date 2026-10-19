"""Imports every model so that Base.metadata knows all tables (Alembic, tests)."""

from advocondo.auth.models import PasswordResetLink, UserSession
from advocondo.metas.models import Goal
from advocondo.users.models import User

__all__ = ["Goal", "PasswordResetLink", "User", "UserSession"]
