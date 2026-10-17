from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from advocondo.condominios.repository import CondominiumRepository
from advocondo.users.models import Role
from tests.fixtures.auth import AuthenticateAs
from tests.fixtures.condominios import CreateCondominium
from tests.fixtures.users import CreateUser

MIRANTE = {
    "name": "Residencial Mirante",
    "cnpj": "14.447.918/0001-98",
    "zip_code": "12345-678",
    "street": "Avenida 26 de Setembro",
    "neighborhood": "Vicente Pires",
    "city": "Brasília",
    "state": "DF",
    "manager_name": "Lucas Gonçalves Castro",
    "manager_email": "lucas@example.com",
    "manager_phone": "(61) 91234-5678",
    "contract_start_date": "2026-01-01",
    "contract_renewal_date": "2027-01-01",
}


@pytest.fixture
def operator_headers(
    create_user: CreateUser, authenticate_as: AuthenticateAs
) -> dict[str, str]:
    return authenticate_as(create_user(role=Role.OPERATOR))


def register(
    client: TestClient, headers: dict[str, str], payload: dict[str, Any]
) -> httpx.Response:
    response: httpx.Response = client.post(
        "/condominiums", json=payload, headers=headers
    )
    return response


class TestRegisterCondominium:
    def test_operator_registers_a_condominium(
        self, db_client: TestClient, operator_headers: dict[str, str]
    ) -> None:
        """US12"""
        response = register(db_client, operator_headers, MIRANTE)

        assert response.status_code == 201
        body = response.json()
        assert body["name"] == "Residencial Mirante"
        assert body["cnpj"] == "14447918000198"
        assert body["manager_phone"] == "61912345678"
        assert body["contract_renewal_date"] == "2027-01-01"

    def test_only_the_name_is_required(
        self, db_client: TestClient, operator_headers: dict[str, str]
    ) -> None:
        response = register(db_client, operator_headers, {"name": "Cond. Lake View"})

        assert response.status_code == 201
        assert response.json()["cnpj"] is None

    def test_cnpj_already_registered_is_refused(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        create_condominium: CreateCondominium,
    ) -> None:
        create_condominium(cnpj="14447918000198")

        response = register(db_client, operator_headers, MIRANTE)

        assert response.status_code == 409
        assert response.json()["detail"] == "Já existe um condomínio com este CNPJ."

    def test_database_refuses_a_duplicated_cnpj_that_slipped_past_the_check(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        create_condominium: CreateCondominium,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Two simultaneous requests can both pass the check made by the service."""
        create_condominium(cnpj="14447918000198")
        monkeypatch.setattr(CondominiumRepository, "get_by_cnpj", lambda *_: None)

        response = register(db_client, operator_headers, MIRANTE)

        assert response.status_code == 409

    def test_condominiums_without_cnpj_do_not_conflict(
        self, db_client: TestClient, operator_headers: dict[str, str]
    ) -> None:
        for _ in range(2):
            response = register(db_client, operator_headers, {"name": "Sem CNPJ"})
            assert response.status_code == 201

    def test_renewal_before_the_start_of_the_contract_is_refused(
        self, db_client: TestClient, operator_headers: dict[str, str]
    ) -> None:
        payload = {**MIRANTE, "contract_renewal_date": "2025-12-31"}

        response = register(db_client, operator_headers, payload)

        assert response.status_code == 422
        assert response.json()["detail"] == (
            "A data de renovação não pode ser anterior ao início do contrato."
        )

    def test_invalid_cnpj_is_refused(
        self, db_client: TestClient, operator_headers: dict[str, str]
    ) -> None:
        payload = {**MIRANTE, "cnpj": "14.447.918/0001-99"}

        assert register(db_client, operator_headers, payload).status_code == 422


class TestOnlyOfficeStaffManagesCondominiums:
    def test_request_without_login_is_refused(self, db_client: TestClient) -> None:
        assert register(db_client, {}, MIRANTE).status_code == 401

    def test_client_user_is_refused(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
    ) -> None:
        headers = authenticate_as(create_user(role=Role.CLIENT))

        assert register(db_client, headers, MIRANTE).status_code == 403

    def test_administrator_is_allowed(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
    ) -> None:
        headers = authenticate_as(create_user(role=Role.ADMIN))

        assert register(db_client, headers, MIRANTE).status_code == 201
