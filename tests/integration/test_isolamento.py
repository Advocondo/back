"""Garante que cada teste começa com o banco limpo.

Também é um exemplo de teste parametrizado + integração: cada caso grava uma
linha e confere que ela é a única, o que só é verdade se os dados do caso
anterior foram descartados.
"""

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from advocondo.condominios.models import Condominio


@pytest.mark.parametrize("nome", ["primeiro", "segundo", "terceiro"])
def test_cada_teste_comeca_com_banco_limpo(db_session: Session, nome: str) -> None:
    db_session.add(Condominio(nome=nome))
    db_session.commit()

    assert db_session.scalar(select(func.count()).select_from(Condominio)) == 1
    assert db_session.scalar(select(Condominio.nome)) == nome
