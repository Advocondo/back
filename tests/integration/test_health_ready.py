"""Exemplo de teste de integração: API + banco de dados de teste."""

from fastapi.testclient import TestClient


def test_readiness_verifica_o_banco(db_client: TestClient) -> None:
    response = db_client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"database": "ok"}}
