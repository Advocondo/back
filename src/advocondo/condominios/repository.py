"""Persistência de condomínios: consultas e escrita, sem regra de negócio.

Não faz commit; quem fecha a transação é o service.
"""

from collections.abc import Sequence

from psycopg.errors import UniqueViolation
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from advocondo.condominios.exceptions import CnpjAlreadyRegisteredError
from advocondo.condominios.models import Condominio

_CNPJ_UNIQUE = "condominios_cnpj_key"


def get(session: Session, condominio_id: int) -> Condominio | None:
    return session.get(Condominio, condominio_id)


def get_by_cnpj(session: Session, cnpj: str) -> Condominio | None:
    return session.scalar(select(Condominio).where(Condominio.cnpj == cnpj))


def search(
    session: Session, *, q: str | None, limit: int, offset: int
) -> Sequence[Condominio]:
    """Busca por nome do condomínio ou do síndico (parcial, sem diferenciar caixa)."""
    stmt = select(Condominio).order_by(Condominio.nome, Condominio.id)
    if q and (term := q.strip()):
        # % e _ digitados pelo usuário são literais, não curingas.
        escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        stmt = stmt.where(
            or_(
                Condominio.nome.ilike(pattern, escape="\\"),
                Condominio.sindico_nome.ilike(pattern, escape="\\"),
            )
        )
    return session.scalars(stmt.limit(limit).offset(offset)).all()


def save(session: Session, condominio: Condominio) -> None:
    """Grava (insert ou update) e recarrega os valores gerados pelo banco."""
    session.add(condominio)
    try:
        session.flush()
    except IntegrityError as exc:
        # A checagem prévia do service não pega duas requisições simultâneas;
        # a restrição UNIQUE do banco é a garantia final.
        orig = exc.orig
        if (
            isinstance(orig, UniqueViolation)
            and orig.diag.constraint_name == _CNPJ_UNIQUE
        ):
            raise CnpjAlreadyRegisteredError(condominio.cnpj) from exc
        raise
    session.refresh(condominio)
