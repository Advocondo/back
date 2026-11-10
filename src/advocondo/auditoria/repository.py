import enum
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import ColumnElement, Select, String, func, literal, select, union_all
from sqlalchemy.orm import Session, joinedload

from advocondo.acordos.models import Agreement, AgreementEditLog
from advocondo.parcelas.models import Installment, InstallmentChangeLog
from advocondo.users.models import UserAuditLog


class AuditCategory(enum.StrEnum):
    """Financeiro: parcelas e acordos (US31 e US19). Usuários: gestão de usuários (US11)."""

    FINANCIAL = "financial"
    USERS = "users"


class AuditSource(enum.StrEnum):
    INSTALLMENT = "installment"
    AGREEMENT = "agreement"
    USER = "user"


CATEGORY_SOURCES = {
    AuditCategory.FINANCIAL: (AuditSource.INSTALLMENT, AuditSource.AGREEMENT),
    AuditCategory.USERS: (AuditSource.USER,),
}


@dataclass(frozen=True)
class AuditFilters:
    actor_id: uuid.UUID | None = None
    # Limites em UTC, já convertidos do dia no Brasil: `start` entra, `end` não.
    start: datetime | None = None
    end: datetime | None = None
    category: AuditCategory | None = None


@dataclass(frozen=True)
class AuditRef:
    source: AuditSource
    id: uuid.UUID


class AuditTrailRepository:
    """Junta os três registros de auditoria em uma lista só, ordenada pela data."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def _sources(self) -> dict[AuditSource, Select[*tuple[Any, ...]]]:
        return {
            AuditSource.INSTALLMENT: select(
                literal(AuditSource.INSTALLMENT.value, String).label("source"),
                InstallmentChangeLog.id.label("id"),
                InstallmentChangeLog.changed_at.label("occurred_at"),
                InstallmentChangeLog.changed_by_id.label("actor_id"),
            ),
            AuditSource.AGREEMENT: select(
                literal(AuditSource.AGREEMENT.value, String).label("source"),
                AgreementEditLog.id.label("id"),
                AgreementEditLog.edited_at.label("occurred_at"),
                AgreementEditLog.edited_by_id.label("actor_id"),
            ),
            AuditSource.USER: select(
                literal(AuditSource.USER.value, String).label("source"),
                UserAuditLog.id.label("id"),
                UserAuditLog.created_at.label("occurred_at"),
                UserAuditLog.actor_id.label("actor_id"),
            ),
        }

    def page(
        self, filters: AuditFilters, limit: int, offset: int
    ) -> tuple[int, list[AuditRef]]:
        """O total que atende aos filtros e as referências da página, da mais recente
        para a mais antiga."""
        sources = self._sources()
        wanted = (
            CATEGORY_SOURCES[filters.category] if filters.category else tuple(sources)
        )
        trail = union_all(*(sources[source] for source in wanted)).subquery("trail")

        conditions: list[ColumnElement[bool]] = []
        if filters.actor_id is not None:
            conditions.append(trail.c.actor_id == filters.actor_id)
        if filters.start is not None:
            conditions.append(trail.c.occurred_at >= filters.start)
        if filters.end is not None:
            conditions.append(trail.c.occurred_at < filters.end)

        total = self._session.scalar(
            select(func.count()).select_from(trail).where(*conditions)
        )
        rows = self._session.execute(
            select(trail.c.source, trail.c.id)
            .where(*conditions)
            .order_by(trail.c.occurred_at.desc(), trail.c.id.desc())
            .limit(limit)
            .offset(offset)
        ).all()
        return total or 0, [AuditRef(AuditSource(source), id_) for source, id_ in rows]

    def installment_logs(
        self, ids: Sequence[uuid.UUID]
    ) -> list[tuple[InstallmentChangeLog, Installment]]:
        rows = self._session.execute(
            select(InstallmentChangeLog, Installment)
            .join(Installment, Installment.id == InstallmentChangeLog.installment_id)
            .options(joinedload(Installment.agreement))
            .where(InstallmentChangeLog.id.in_(ids))
        ).all()
        return [(log, installment) for log, installment in rows]

    def agreement_logs(
        self, ids: Sequence[uuid.UUID]
    ) -> list[tuple[AgreementEditLog, Agreement]]:
        rows = self._session.execute(
            select(AgreementEditLog, Agreement)
            .join(Agreement, Agreement.id == AgreementEditLog.agreement_id)
            .where(AgreementEditLog.id.in_(ids))
        ).all()
        return [(log, agreement) for log, agreement in rows]

    def user_logs(self, ids: Sequence[uuid.UUID]) -> list[UserAuditLog]:
        return list(
            self._session.scalars(
                select(UserAuditLog)
                .options(joinedload(UserAuditLog.user), joinedload(UserAuditLog.actor))
                .where(UserAuditLog.id.in_(ids))
            ).all()
        )
