from datetime import date
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


ALL_NAMES_IN_ORDER = ["Cond. Parque das Águas", "Ed. 100% Century", "Res. Villa Verde"]


class TestSearchCondominiums:
    @pytest.fixture(autouse=True)
    def three_condominiums(self, create_condominium: CreateCondominium) -> None:
        create_condominium(name="Res. Villa Verde", manager_name="Marcos Tavares")
        create_condominium(name="Cond. Parque das Águas", manager_name="Rita Belmonte")
        create_condominium(name="Ed. 100% Century", manager_name="Conselho Gestor")

    @pytest.mark.parametrize(
        ("search", "expected_names"),
        [
            pytest.param(None, ALL_NAMES_IN_ORDER, id="no-search-lists-all-by-name"),
            pytest.param("villa", ["Res. Villa Verde"], id="part-of-the-name"),
            pytest.param("RITA", ["Cond. Parque das Águas"], id="manager-name"),
            pytest.param("100%", ["Ed. 100% Century"], id="percent-is-literal"),
            pytest.param("0%", ["Ed. 100% Century"], id="percent-is-not-wildcard"),
            pytest.param("  ", ALL_NAMES_IN_ORDER, id="blank-search-lists-all"),
            pytest.param("xyz", [], id="nothing-found"),
        ],
    )
    def test_search_by_condominium_or_manager_name(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        search: str | None,
        expected_names: list[str],
    ) -> None:
        params = {"search": search} if search is not None else {}

        response = db_client.get(
            "/condominiums", params=params, headers=operator_headers
        )

        assert [item["name"] for item in response.json()] == expected_names

    def test_list_is_paginated(
        self, db_client: TestClient, operator_headers: dict[str, str]
    ) -> None:
        response = db_client.get(
            "/condominiums", params={"limit": 1, "offset": 1}, headers=operator_headers
        )

        assert [item["name"] for item in response.json()] == ["Ed. 100% Century"]


class TestGetCondominium:
    def test_returns_the_condominium(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        create_condominium: CreateCondominium,
    ) -> None:
        condominium = create_condominium(name="Res. Terra Nova")

        response = db_client.get(
            f"/condominiums/{condominium.id}", headers=operator_headers
        )

        assert response.status_code == 200
        assert response.json()["name"] == "Res. Terra Nova"

    def test_unknown_condominium_is_not_found(
        self, db_client: TestClient, operator_headers: dict[str, str]
    ) -> None:
        response = db_client.get(
            "/condominiums/00000000-0000-0000-0000-000000000000",
            headers=operator_headers,
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Condomínio não encontrado."


def update(
    client: TestClient,
    headers: dict[str, str],
    condominium_id: object,
    payload: dict[str, Any],
) -> httpx.Response:
    response: httpx.Response = client.patch(
        f"/condominiums/{condominium_id}", json=payload, headers=headers
    )
    return response


class TestUpdateCondominium:
    def test_condominium_can_be_edited_after_registered(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        create_condominium: CreateCondominium,
    ) -> None:
        """US12-CA02"""
        condominium = create_condominium(
            name="Res. Villa Verde", cnpj="14447918000198", manager_name="Marcos"
        )

        response = update(
            db_client,
            operator_headers,
            condominium.id,
            {"manager_name": "Nova Administradora", "state": "go"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["manager_name"] == "Nova Administradora"
        assert body["state"] == "GO"
        assert body["name"] == "Res. Villa Verde"
        assert body["cnpj"] == "14447918000198"

    def test_optional_field_sent_as_null_is_cleared(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        create_condominium: CreateCondominium,
    ) -> None:
        condominium = create_condominium(manager_email="rita@example.com")

        response = update(
            db_client, operator_headers, condominium.id, {"manager_email": None}
        )

        assert response.json()["manager_email"] is None

    def test_cnpj_of_another_condominium_is_refused(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        create_condominium: CreateCondominium,
    ) -> None:
        create_condominium(cnpj="14447918000198")
        other = create_condominium(name="Outro", cnpj="11222333000181")

        response = update(
            db_client, operator_headers, other.id, {"cnpj": "14447918000198"}
        )

        assert response.status_code == 409

    def test_sending_its_own_cnpj_again_is_accepted(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        create_condominium: CreateCondominium,
    ) -> None:
        condominium = create_condominium(cnpj="14447918000198")

        response = update(
            db_client, operator_headers, condominium.id, {"cnpj": "14447918000198"}
        )

        assert response.status_code == 200

    def test_renewal_is_checked_against_the_stored_start_date(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        create_condominium: CreateCondominium,
    ) -> None:
        condominium = create_condominium(contract_start_date=date(2026, 1, 1))

        response = update(
            db_client,
            operator_headers,
            condominium.id,
            {"contract_renewal_date": "2025-12-31"},
        )

        assert response.status_code == 422

    def test_unknown_condominium_is_not_found(
        self, db_client: TestClient, operator_headers: dict[str, str]
    ) -> None:
        response = update(
            db_client,
            operator_headers,
            "00000000-0000-0000-0000-000000000000",
            {"name": "X"},
        )

        assert response.status_code == 404
