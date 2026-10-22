"""Imports every model so that Base.metadata knows all tables (Alembic, tests)."""

from advocondo.acordos.models import Agreement, LawyerAssignment
from advocondo.auth.models import PasswordResetLink, UserSession
from advocondo.condominios.models import Condominium
from advocondo.devedores.models import Debtor
from advocondo.parcelas.models import Installment, InstallmentPayment
from advocondo.users.models import User, UserAuditLog, UserCondominium

__all__ = [
    "Agreement",
    "Condominium",
    "Debtor",
    "Installment",
    "InstallmentPayment",
    "LawyerAssignment",
    "PasswordResetLink",
    "User",
    "UserAuditLog",
    "UserCondominium",
    "UserSession",
]
