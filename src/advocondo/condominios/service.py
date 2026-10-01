"""Regras de negócio do cadastro de condomínios (US12).

Único lugar do módulo que faz commit. Acesso a dados só pelo repository.
"""

from collections.abc import Sequence

from sqlalchemy.orm import Session

from advocondo.condominios import repository
from advocondo.condominios.exceptions import (
    CnpjAlreadyRegisteredError,
    CondominioNotFoundError,
)
from advocondo.condominios.models import Condominio
from advocondo.condominios.schemas import CondominioCreate, CondominioUpdate


def _ensure_cnpj_available(
    session: Session, cnpj: str | None, *, ignore_id: int | None = None
) -> None:
    if cnpj is None:
        return
    found = repository.get_by_cnpj(session, cnpj)
    if found is not None and found.id != ignore_id:
        raise CnpjAlreadyRegisteredError(cnpj)


def create(session: Session, data: CondominioCreate) -> Condominio:
    _ensure_cnpj_available(session, data.cnpj)
    condominio = Condominio(**data.model_dump())
    repository.save(session, condominio)
    session.commit()
    return condominio


def get(session: Session, condominio_id: int) -> Condominio:
    condominio = repository.get(session, condominio_id)
    if condominio is None:
        raise CondominioNotFoundError(condominio_id)
    return condominio


def search(
    session: Session, *, q: str | None = None, limit: int = 50, offset: int = 0
) -> Sequence[Condominio]:
    return repository.search(session, q=q, limit=limit, offset=offset)


def update(session: Session, condominio_id: int, data: CondominioUpdate) -> Condominio:
    condominio = get(session, condominio_id)
    changes = data.model_dump(exclude_unset=True)
    if "cnpj" in changes:
        _ensure_cnpj_available(session, changes["cnpj"], ignore_id=condominio.id)
    for field, value in changes.items():
        setattr(condominio, field, value)
    repository.save(session, condominio)
    session.commit()
    return condominio
