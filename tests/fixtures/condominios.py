from typing import Any, Protocol

import pytest
from sqlalchemy.orm import Session

from advocondo.condominios.models import Condominium


class CreateCondominium(Protocol):
    def __call__(self, **fields: Any) -> Condominium: ...


@pytest.fixture
def create_condominium(db_session: Session) -> CreateCondominium:
    """Saves a condominium straight in the database; fields override the defaults."""

    def create(**fields: Any) -> Condominium:
        condominium = Condominium(**{"name": "Residencial Mirante", **fields})
        db_session.add(condominium)
        db_session.flush()
        return condominium

    return create
