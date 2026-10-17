"""Imports every model so that Base.metadata knows all tables (Alembic, tests)."""

from advocondo.auth.models import UserSession
from advocondo.users.models import User

__all__ = ["User", "UserSession"]
