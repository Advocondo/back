"""Imports every model so that Base.metadata knows all tables (Alembic, tests)."""

from advocondo.acordos.models import Agreement, LawyerAssignment
from advocondo.auth.models import PasswordResetLink, UserSession
from advocondo.metas.models import Goal
from advocondo.users.models import User

__all__ = ["Goal", "PasswordResetLink", "User", "UserSession"]
from advocondo.condominios.models import Condominium
from advocondo.devedores.models import Debtor
from advocondo.landing.models import LandingBlock, LandingImage
from advocondo.parcelas.models import Installment, InstallmentPayment
from advocondo.users.models import UserAuditLog, UserCondominium

__all__ = [
    "Agreement",
    "Condominium",
    "Debtor",
    "Installment",
    "InstallmentPayment",
    "LandingBlock",
    "LandingImage",
    "LawyerAssignment",
    "PasswordResetLink",
    "User",
    "UserAuditLog",
    "UserCondominium",
    "UserSession",
]
