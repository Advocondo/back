"""Imports every model so that Base.metadata knows all tables (Alembic, tests)."""

from advocondo.auth.models import PasswordResetLink, UserSession
from advocondo.condominios.models import Condominium
from advocondo.devedores.models import Debtor
from advocondo.users.models import User, UserCondominium

__all__ = [
    "Condominium",
    "Debtor",
    "PasswordResetLink",
    "User",
    "UserCondominium",
    "UserSession",
]
