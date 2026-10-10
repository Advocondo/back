"""Imports every model so that Base.metadata knows all tables (Alembic, tests)."""

from advocondo.users.models import User

__all__ = ["User"]
