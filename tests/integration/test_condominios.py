"""US12 — Cadastrar condomínio. Ver docs/testes.md para as fixtures."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

BASE: dict[str, Any] = {
    "nome": "Residencial Mirante",
    "cnpj": "14.447.918/0001-98",
    "cep": "12345-678",
    "logradouro": "Avenida 26 de Setembro",
    "bairro": "Vicente Pires",
    "cidade": "Brasília",
    "uf": "DF",
    "sindico_nome": "Lucas Gonçalves Castro",
    "sindico_email": "lucas@example.com",
    "sindico_telefone": "(61) 91234-5678",
    "contrato_inicio": "2026-01-01",
    "contrato_renovacao": "2027-01-01",
}


def _create(client: TestClient, **overrides: Any) -> dict[str, Any]:
    response = client.post("/condominios", json={**BASE, **overrides})
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def test_cadastra_condominio_com_todos_os_dados(db_client: TestClient) -> None:
    body = _create(db_client)

    assert body["id"] > 0
    assert body["nome"] == "Residencial Mirante"
    assert body["cnpj"] == "14447918000198"
    assert body["sindico_telefone"] == "61912345678"
    assert db_client.get(f"/condominios/{body['id']}").json() == body


def test_cadastra_apenas_com_o_nome(db_client: TestClient) -> None:
    body = _create_minimal(db_client)
    assert body["cnpj"] is None


def _create_minimal(client: TestClient) -> dict[str, Any]:
    response = client.post("/condominios", json={"nome": "Só Nome"})
    assert response.status_code == 201
    body: dict[str, Any] = response.json()
    return body


def test_nome_obrigatorio(db_client: TestClient) -> None:
    response = db_client.post("/condominios", json={"cnpj": BASE["cnpj"]})
    assert response.status_code == 422


def test_cnpj_duplicado_retorna_409(db_client: TestClient) -> None:
    _create(db_client)
    response = db_client.post("/condominios", json={**BASE, "nome": "Outro"})
    assert response.status_code == 409


def test_condominios_sem_cnpj_podem_se_repetir(db_client: TestClient) -> None:
    _create_minimal(db_client)
    _create_minimal(db_client)


def test_US12_CA02_edita_condominio_depois_de_cadastrado(
    db_client: TestClient,
) -> None:
    created = _create(db_client)

    response = db_client.patch(
        f"/condominios/{created['id']}",
        json={"sindico_nome": "Nova Administradora", "uf": "go"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["sindico_nome"] == "Nova Administradora"
    assert body["uf"] == "GO"
    # O que não foi enviado permanece como estava.
    assert body["nome"] == created["nome"]
    assert body["cnpj"] == created["cnpj"]


def test_edicao_pode_limpar_campo_opcional(db_client: TestClient) -> None:
    created = _create(db_client)
    response = db_client.patch(
        f"/condominios/{created['id']}", json={"sindico_email": None}
    )
    assert response.status_code == 200
    assert response.json()["sindico_email"] is None


def test_edicao_nao_remove_o_nome(db_client: TestClient) -> None:
    created = _create(db_client)
    response = db_client.patch(f"/condominios/{created['id']}", json={"nome": None})
    assert response.status_code == 422


def test_edicao_nao_aceita_cnpj_de_outro_condominio(db_client: TestClient) -> None:
    _create(db_client)
    other = _create(db_client, nome="Outro", cnpj="11.222.333/0001-81")
    response = db_client.patch(
        f"/condominios/{other['id']}", json={"cnpj": BASE["cnpj"]}
    )
    assert response.status_code == 409


def test_edicao_pode_reenviar_o_proprio_cnpj(db_client: TestClient) -> None:
    created = _create(db_client)
    response = db_client.patch(
        f"/condominios/{created['id']}", json={"cnpj": BASE["cnpj"], "nome": "Novo"}
    )
    assert response.status_code == 200


@pytest.mark.parametrize("method", ["get", "patch"])
def test_condominio_inexistente_retorna_404(db_client: TestClient, method: str) -> None:
    kwargs = {"json": {"nome": "X"}} if method == "patch" else {}
    response = getattr(db_client, method)("/condominios/999999", **kwargs)
    assert response.status_code == 404


@pytest.mark.parametrize(
    ("q", "esperado"),
    [
        (None, ["Cond. Parque", "Ed. Century", "Res. Villa"]),
        ("villa", ["Res. Villa"]),
        ("RITA", ["Cond. Parque"]),  # busca pelo síndico, sem diferenciar caixa
        ("  parque ", ["Cond. Parque"]),
        ("100%", []),  # '%' é literal, não curinga
        ("xyz", []),
    ],
)
def test_busca_por_condominio_ou_sindico(
    db_client: TestClient, q: str | None, esperado: list[str]
) -> None:
    _create(db_client, nome="Res. Villa", cnpj=None, sindico_nome="Marcos")
    _create(db_client, nome="Cond. Parque", cnpj=None, sindico_nome="Rita Belmonte")
    _create(db_client, nome="Ed. Century", cnpj=None, sindico_nome="Conselho")

    response = db_client.get("/condominios", params={"q": q} if q else None)

    assert [c["nome"] for c in response.json()] == esperado


def test_listagem_pagina(db_client: TestClient) -> None:
    for i in range(3):
        _create(db_client, nome=f"Cond {i}", cnpj=None)
    response = db_client.get("/condominios", params={"limit": 2, "offset": 1})
    assert [c["nome"] for c in response.json()] == ["Cond 1", "Cond 2"]


def test_corrida_de_cnpj_e_barrada_pelo_banco(
    db_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Se a checagem prévia não pegar (duas requisições ao mesmo tempo), a
    restrição UNIQUE do banco ainda devolve 409."""
    _create(db_client)
    monkeypatch.setattr(
        "advocondo.condominios.service._ensure_cnpj_available", lambda *a, **k: None
    )
    response = db_client.post("/condominios", json={**BASE, "nome": "Outro"})
    assert response.status_code == 409
