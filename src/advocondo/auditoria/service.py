import uuid
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from datetime import date, datetime, time, timedelta
from typing import Any

from advocondo.acordos.models import Agreement, AgreementEditField
from advocondo.auditoria.errors import InvalidAuditPeriodError
from advocondo.auditoria.repository import (
    AuditCategory,
    AuditFilters,
    AuditSource,
    AuditTrailRepository,
)
from advocondo.common.clock import BRAZIL_TIMEZONE
from advocondo.users.models import User

AGREEMENT_EDITED = "agreement_edited"


@dataclass(frozen=True)
class AuditEntry:
    """Uma linha da trilha: quem fez, quando, o quê, em qual alvo e o valor alterado."""

    id: uuid.UUID
    occurred_at: datetime
    category: AuditCategory
    # A movimentação da parcela (US31), "agreement_edited" (US19) ou a ação sobre o
    # usuário (US11), com os mesmos valores das rotas de histórico de cada um.
    action: str
    actor: User | None
    old_value: str | None
    new_value: str | None
    agreement: Agreement | None = None
    installment_number: int | None = None
    field: AgreementEditField | None = None
    target_user: User | None = None
    added_condominiums: list[dict[str, Any]] = dataclass_field(default_factory=list)
    removed_condominiums: list[dict[str, Any]] = dataclass_field(default_factory=list)


@dataclass(frozen=True)
class AuditPage:
    total: int
    entries: list[AuditEntry]


def brazil_day_bounds(
    date_from: date | None, date_to: date | None
) -> tuple[datetime | None, datetime | None]:
    """Os dias valem no horário de Brasília, como no resto do sistema."""
    if date_from is not None and date_to is not None and date_from > date_to:
        raise InvalidAuditPeriodError()
    start = (
        datetime.combine(date_from, time.min, BRAZIL_TIMEZONE) if date_from else None
    )
    end = (
        datetime.combine(date_to + timedelta(days=1), time.min, BRAZIL_TIMEZONE)
        if date_to
        else None
    )
    return start, end


class AuditTrailService:
    def __init__(self, repository: AuditTrailRepository) -> None:
        self._repository = repository

    def list(
        self,
        *,
        limit: int,
        offset: int,
        actor_id: uuid.UUID | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        category: AuditCategory | None = None,
    ) -> AuditPage:
        start, end = brazil_day_bounds(date_from, date_to)
        filters = AuditFilters(
            actor_id=actor_id, start=start, end=end, category=category
        )
        total, refs = self._repository.page(filters, limit, offset)

        def ids(source: AuditSource) -> list[uuid.UUID]:
            return [ref.id for ref in refs if ref.source is source]

        entries: dict[uuid.UUID, AuditEntry] = {}
        for log, installment in self._repository.installment_logs(
            ids(AuditSource.INSTALLMENT)
        ):
            entries[log.id] = AuditEntry(
                id=log.id,
                occurred_at=log.changed_at,
                category=AuditCategory.FINANCIAL,
                action=log.change.value,
                actor=log.changed_by,
                old_value=log.old_value,
                new_value=log.new_value,
                agreement=installment.agreement,
                installment_number=installment.number,
            )
        for edit, agreement in self._repository.agreement_logs(
            ids(AuditSource.AGREEMENT)
        ):
            entries[edit.id] = AuditEntry(
                id=edit.id,
                occurred_at=edit.edited_at,
                category=AuditCategory.FINANCIAL,
                action=AGREEMENT_EDITED,
                actor=edit.edited_by,
                old_value=edit.old_value,
                new_value=edit.new_value,
                agreement=agreement,
                field=edit.field,
            )
        for user_log in self._repository.user_logs(ids(AuditSource.USER)):
            entries[user_log.id] = AuditEntry(
                id=user_log.id,
                occurred_at=user_log.created_at,
                category=AuditCategory.USERS,
                action=user_log.action.value,
                actor=user_log.actor,
                old_value=user_log.old_value,
                new_value=user_log.new_value,
                target_user=user_log.user,
                added_condominiums=user_log.added_condominiums,
                removed_condominiums=user_log.removed_condominiums,
            )
        return AuditPage(total=total, entries=[entries[ref.id] for ref in refs])
