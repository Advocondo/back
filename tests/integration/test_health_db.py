"""Exemplo de teste de integração: API + banco de dados de teste."""

from fastapi.testclient import TestClient


def test_health_db_conecta_no_banco(db_client: TestClient) -> None:
    response = db_client.get("/health/db")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}
