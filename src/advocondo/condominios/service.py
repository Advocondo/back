"""Regras de negócio do cadastro de condomínios (US12).

Único lugar do módulo que faz commit. Acesso a dados só pelo repository.
"""

from collections.abc import Sequence
from datetime import date

from sqlalchemy.orm import Session

from advocondo.condominios import repository
from advocondo.condominios.exceptions import (
    CnpjAlreadyRegisteredError,
    CondominioNotFoundError,
    InvalidContractDatesError,
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


def _ensure_contract_dates(inicio: date | None, renovacao: date | None) -> None:
    if inicio and renovacao and renovacao < inicio:
        raise InvalidContractDatesError


def create(session: Session, data: CondominioCreate) -> Condominio:
    _ensure_cnpj_available(session, data.cnpj)
    _ensure_contract_dates(data.contrato_inicio, data.contrato_renovacao)
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
    # Valida o estado final (gravado + alterações) antes de alterar a entidade:
    # num PATCH só com a renovação, o início vem do banco.
    _ensure_contract_dates(
        changes.get("contrato_inicio", condominio.contrato_inicio),
        changes.get("contrato_renovacao", condominio.contrato_renovacao),
    )
    for field, value in changes.items():
        setattr(condominio, field, value)
    repository.save(session, condominio)
    session.commit()
    return condominio
