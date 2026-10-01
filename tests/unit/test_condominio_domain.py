import pytest

from advocondo.condominios.domain import is_valid_cnpj


@pytest.mark.parametrize("cnpj", ["14447918000198", "11222333000181"])
def test_cnpj_com_digitos_verificadores_corretos(cnpj: str) -> None:
    assert is_valid_cnpj(cnpj)


@pytest.mark.parametrize(
    "cnpj",
    [
        "14447918000199",  # último dígito errado
        "14447918000188",  # penúltimo dígito errado
        "11111111111111",  # todos iguais
        "1444791800019",  # 13 dígitos
        "14.447.918/0001-98",  # com máscara: o schema tira antes
        "",
    ],
)
def test_cnpj_invalido(cnpj: str) -> None:
    assert not is_valid_cnpj(cnpj)
