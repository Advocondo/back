from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from advocondo.condominios.errors import CnpjAlreadyRegisteredError
from advocondo.condominios.models import Condominium

CNPJ_UNIQUE_CONSTRAINT = "uq_condominiums_cnpj"


class CondominiumRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

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
