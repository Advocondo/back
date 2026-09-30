"""Exemplo de teste parametrizado: um mesmo teste, vários casos."""

import pytest
from sqlalchemy.engine import make_url

from tests.support.database import assert_is_test_database

BASE = "postgresql+psycopg://user:pass@localhost:5432"


@pytest.mark.parametrize(
    "database",
    ["advocondo_test", "outro_test"],
)
def test_aceita_banco_de_testes(database: str) -> None:
    assert_is_test_database(make_url(f"{BASE}/{database}"))


@pytest.mark.parametrize(
    "database",
    [
        pytest.param("advocondo", id="banco-de-dev"),
        pytest.param("advocondo_prod", id="banco-de-producao"),
        pytest.param("test_advocondo", id="test-no-inicio"),
        pytest.param("", id="sem-nome"),
    ],
)
def test_recusa_banco_que_nao_e_de_testes(database: str) -> None:
    with pytest.raises(ValueError, match="_test"):
        assert_is_test_database(make_url(f"{BASE}/{database}"))
