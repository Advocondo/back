"""Imports every model so that Base.metadata knows all tables (Alembic, tests)."""

from advocondo.auth.models import PasswordResetLink, UserSession
from advocondo.condominios.models import Condominium
from advocondo.users.models import User

__all__ = ["Condominium", "PasswordResetLink", "User", "UserSession"]
