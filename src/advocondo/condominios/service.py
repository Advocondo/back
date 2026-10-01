"""Regras de negócio do cadastro de condomínios (US12)."""

from collections.abc import Sequence

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from advocondo.condominios.models import Condominio
from advocondo.condominios.schemas import CondominioCreate, CondominioUpdate


class CondominioNotFoundError(Exception):
    pass


class CnpjAlreadyRegisteredError(Exception):
    pass


def _ensure_cnpj_available(
    session: Session, cnpj: str | None, *, ignore_id: int | None = None
) -> None:
    if cnpj is None:
        return
    found = session.scalar(select(Condominio.id).where(Condominio.cnpj == cnpj))
    if found is not None and found != ignore_id:
        raise CnpjAlreadyRegisteredError(cnpj)


def _commit(session: Session, cnpj: str | None) -> None:
    try:
        session.commit()
    except IntegrityError as exc:
        # Corrida entre duas requisições com o mesmo CNPJ.
        session.rollback()
        raise CnpjAlreadyRegisteredError(cnpj) from exc


def create(session: Session, data: CondominioCreate) -> Condominio:
    _ensure_cnpj_available(session, data.cnpj)
    condominio = Condominio(**data.model_dump())
    session.add(condominio)
    _commit(session, data.cnpj)
    session.refresh(condominio)
    return condominio


def get(session: Session, condominio_id: int) -> Condominio:
    condominio = session.get(Condominio, condominio_id)
    if condominio is None:
        raise CondominioNotFoundError(condominio_id)
    return condominio


def search(
    session: Session, *, q: str | None = None, limit: int = 50, offset: int = 0
) -> Sequence[Condominio]:
    """Busca por nome do condomínio ou do síndico (parcial, sem diferenciar caixa)."""
    stmt = select(Condominio).order_by(Condominio.nome, Condominio.id)
    if q and (term := q.strip()):
        pattern = (
            f"%{term.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')}%"
        )
        stmt = stmt.where(
            or_(
                Condominio.nome.ilike(pattern, escape="\\"),
                Condominio.sindico_nome.ilike(pattern, escape="\\"),
            )
        )
    return session.scalars(stmt.limit(limit).offset(offset)).all()


def update(session: Session, condominio_id: int, data: CondominioUpdate) -> Condominio:
    condominio = get(session, condominio_id)
    changes = data.model_dump(exclude_unset=True)
    if "cnpj" in changes:
        _ensure_cnpj_available(session, changes["cnpj"], ignore_id=condominio.id)
    for field, value in changes.items():
        setattr(condominio, field, value)
    _commit(session, changes.get("cnpj"))
    session.refresh(condominio)
    return condominio
