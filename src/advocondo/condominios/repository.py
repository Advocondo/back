import uuid
from collections.abc import Sequence

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from advocondo.condominios.errors import CnpjAlreadyRegisteredError
from advocondo.condominios.models import Condominium

CNPJ_UNIQUE_CONSTRAINT = "uq_condominiums_cnpj"


class CondominiumRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, condominium_id: uuid.UUID) -> Condominium | None:
        return self._session.get(Condominium, condominium_id)

    def search(
        self, text: str | None, limit: int, offset: int
    ) -> Sequence[Condominium]:
        """Condominiums whose name or manager name contains `text`, ignoring case."""
        query = select(Condominium).order_by(Condominium.name, Condominium.id)
        if text:
            pattern = f"%{escape_like_wildcards(text)}%"
            query = query.where(
                or_(
                    Condominium.name.ilike(pattern, escape="\\"),
                    Condominium.manager_name.ilike(pattern, escape="\\"),
                )
            )
        return self._session.scalars(query.limit(limit).offset(offset)).all()

    def get_by_cnpj(self, cnpj: str) -> Condominium | None:
        return self._session.scalar(select(Condominium).where(Condominium.cnpj == cnpj))

    def add(self, condominium: Condominium) -> None:
        self._session.add(condominium)
        self._flush()

    def _flush(self) -> None:
        try:
            self._session.flush()
        except IntegrityError as error:
            # The service checks the CNPJ first, but two simultaneous requests can
            # both pass that check; the unique constraint is the final guarantee.
            violated_constraint = getattr(error.orig, "diag", None)
            if getattr(violated_constraint, "constraint_name", None) == (
                CNPJ_UNIQUE_CONSTRAINT
            ):
                raise CnpjAlreadyRegisteredError() from error
            raise


def escape_like_wildcards(text: str) -> str:
    """Typed % and _ are searched literally, not as LIKE wildcards."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
