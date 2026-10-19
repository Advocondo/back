from typing import Any, Protocol

import pytest
from sqlalchemy.orm import Session

from advocondo.condominios.models import Condominium
from advocondo.devedores.models import Debtor


class CreateDebtor(Protocol):
    def __call__(self, condominium: Condominium, **fields: Any) -> Debtor: ...


@pytest.fixture
def create_debtor(db_session: Session) -> CreateDebtor:
    """Saves a debtor of `condominium` straight in the database."""

    def create(condominium: Condominium, **fields: Any) -> Debtor:
        defaults = {"name": "José Simão", "unit": "Bloco B 304", "phone": "61912345678"}
        debtor = Debtor(condominium_id=condominium.id, **{**defaults, **fields})
        db_session.add(debtor)
        db_session.flush()
        return debtor

    return create
