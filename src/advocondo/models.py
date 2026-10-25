"""Imports every model so that Base.metadata knows all tables (Alembic, tests)."""

from advocondo.acordos.models import Agreement, AgreementEditLog, LawyerAssignment
from advocondo.auth.models import PasswordResetLink, UserSession
from advocondo.condominios.models import Condominium
from advocondo.devedores.models import Debtor
from advocondo.documentos.models import AgreementDocument, AgreementPdf
from advocondo.landing.models import LandingBlock, LandingImage
from advocondo.metas.models import Goal
from advocondo.notificacoes.models import Notification
from advocondo.parcelas.models import Installment, InstallmentPayment
from advocondo.users.models import User, UserAuditLog, UserCondominium

__all__ = [
    "Agreement",
    "AgreementDocument",
    "AgreementEditLog",
    "AgreementPdf",
    "Condominium",
    "Debtor",
    "Goal",
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
