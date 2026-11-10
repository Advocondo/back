import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from advocondo.acordos.models import AgreementEditField
from advocondo.acordos.schemas import DebtorSummary
from advocondo.auditoria.repository import AuditCategory
from advocondo.users.schemas import ActorResponse, UserCondominiumResponse


class AuditCondominiumSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str


class AuditAgreementTarget(BaseModel):
    """O acordo alterado, com o que a tela mostra para reconhecê-lo."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    debtor: DebtorSummary
    condominium: AuditCondominiumSummary


class AuditEntryResponse(BaseModel):
    """Uma linha da trilha. Nas ações financeiras vem `agreement`, com
    `installment_number` nas movimentações de parcela e `field` nas edições do acordo.
    Nas ações sobre usuários vem `target_user`."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    occurred_at: datetime
    category: AuditCategory
    action: str
    actor: ActorResponse | None
    old_value: str | None
    new_value: str | None
    agreement: AuditAgreementTarget | None
    installment_number: int | None
    field: AgreementEditField | None
    target_user: ActorResponse | None
    added_condominiums: list[UserCondominiumResponse]
    removed_condominiums: list[UserCondominiumResponse]


class AuditTrailResponse(BaseModel):
    total: int
    entries: list[AuditEntryResponse]
