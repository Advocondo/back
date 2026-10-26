"""Imports every model so that Base.metadata knows all tables (Alembic, tests)."""

from advocondo.acordos.models import Agreement, AgreementEditLog, LawyerAssignment
from advocondo.auth.models import PasswordResetLink, UserSession
from advocondo.condominios.models import Condominium
from advocondo.devedores.models import Debtor
from advocondo.documentos.models import (
    AgreementDocument,
    AgreementDocumentFile,
    AgreementPdf,
)
from advocondo.landing.models import LandingBlock, LandingImage
from advocondo.metas.models import Goal
from advocondo.notificacoes.models import ClientNotificationLog, Notification
from advocondo.painel_cliente.models import CondominiumMonthlyReport
from advocondo.parcelas.models import (
    Installment,
    InstallmentChangeLog,
    InstallmentPayment,
)
from advocondo.users.models import User, UserAuditLog, UserCondominium

__all__ = [
    "Agreement",
    "AgreementDocument",
    "AgreementDocumentFile",
    "AgreementEditLog",
    "AgreementPdf",
    "ClientNotificationLog",
    "Condominium",
    "CondominiumMonthlyReport",
    "Debtor",
    "Goal",
    "Installment",
    "InstallmentChangeLog",
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
