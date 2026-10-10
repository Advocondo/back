"""Garante que cada teste começa com o banco limpo.

Também é um exemplo de teste parametrizado + integração: cada caso grava uma
linha e confere que ela é a única, o que só é verdade se os dados do caso
anterior foram descartados.
"""

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, String, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


class RascunhoBase(DeclarativeBase):
    """Fora do Base da aplicação: não é modelo do domínio e não tem migration."""


class Rascunho(RascunhoBase):
    """Tabela usada só nos testes, até existirem os modelos do domínio (#42)."""

    __tablename__ = "rascunho_teste"

    id: Mapped[int] = mapped_column(primary_key=True)
    texto: Mapped[str] = mapped_column(String(100))


@pytest.fixture(scope="module", autouse=True)
def tabela_rascunho(db_engine: Engine) -> Iterator[None]:
    RascunhoBase.metadata.create_all(db_engine)
    yield
    RascunhoBase.metadata.drop_all(db_engine)


@pytest.mark.parametrize("texto", ["primeiro", "segundo", "terceiro"])
def test_cada_teste_comeca_com_banco_limpo(db_session: Session, texto: str) -> None:
    db_session.add(Rascunho(texto=texto))
    db_session.commit()

    assert db_session.scalar(select(func.count()).select_from(Rascunho)) == 1
    assert db_session.scalar(select(Rascunho.texto)) == texto
