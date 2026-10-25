"""Imports every model so that Base.metadata knows all tables (Alembic, tests)."""

from advocondo.acordos.models import Agreement, AgreementEditLog, LawyerAssignment
from advocondo.auth.models import PasswordResetLink, UserSession
from advocondo.metas.models import Goal
from advocondo.users.models import User

__all__ = ["Goal", "PasswordResetLink", "User", "UserSession"]
from advocondo.condominios.models import Condominium
from advocondo.devedores.models import Debtor
from advocondo.documentos.models import AgreementPdf
from advocondo.landing.models import LandingBlock, LandingImage
from advocondo.notificacoes.models import Notification
from advocondo.parcelas.models import Installment, InstallmentPayment
from advocondo.users.models import UserAuditLog, UserCondominium

__all__ = [
    "Agreement",
    "AgreementEditLog",
    "AgreementPdf",
    "Condominium",
    "Debtor",
    "Installment",
    "InstallmentPayment",
    "LandingBlock",
    "LandingImage",
    "LawyerAssignment",
    "Notification",
    "PasswordResetLink",
    "User",
    "UserAuditLog",
    "UserCondominium",
    "UserSession",
]
