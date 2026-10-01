import pytest
from pydantic import ValidationError

from advocondo.condominios.schemas import CondominioCreate, CondominioUpdate

CNPJ_VALIDO = "14.447.918/0001-98"


@pytest.mark.parametrize("cnpj", [CNPJ_VALIDO, "14447918000198", " 14447918000198 "])
def test_cnpj_aceita_com_ou_sem_mascara_e_normaliza(cnpj: str) -> None:
    assert CondominioCreate(nome="Mirante", cnpj=cnpj).cnpj == "14447918000198"


@pytest.mark.parametrize("cnpj", ["14447918000199", "11111111111111", "123", "abc", ""])
def test_cnpj_invalido_e_rejeitado(cnpj: str) -> None:
    with pytest.raises(ValidationError):
        CondominioCreate(nome="Mirante", cnpj=cnpj)


def test_nome_e_obrigatorio_e_nao_pode_ser_vazio() -> None:
    with pytest.raises(ValidationError):
        CondominioCreate.model_validate({})
    with pytest.raises(ValidationError):
        CondominioCreate(nome="   ")


def test_campos_com_mascara_sao_normalizados() -> None:
    condominio = CondominioCreate(
        nome="Mirante",
        cep="12345-678",
        uf="df",
        sindico_telefone="(61) 91234-5678",
    )
    assert (condominio.cep, condominio.uf, condominio.sindico_telefone) == (
        "12345678",
        "DF",
        "61912345678",
    )


def test_renovacao_nao_pode_ser_anterior_ao_inicio() -> None:
    with pytest.raises(ValidationError, match="renovação"):
        CondominioCreate(
            nome="Mirante",
            contrato_inicio="2026-01-01",  # type: ignore[arg-type]
            contrato_renovacao="2025-12-31",  # type: ignore[arg-type]
        )


def test_update_nao_aceita_nome_nulo_mas_aceita_ausente() -> None:
    assert CondominioUpdate().nome is None
    with pytest.raises(ValidationError):
        CondominioUpdate(nome=None)
