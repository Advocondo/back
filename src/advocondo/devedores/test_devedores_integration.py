from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from advocondo.condominios.models import Condominium
from advocondo.users.models import Role
from tests.fixtures.auth import AuthenticateAs
from tests.fixtures.condominios import CreateCondominium
from tests.fixtures.devedores import CreateDebtor
from tests.fixtures.users import CreateUser

UNKNOWN_ID = "00000000-0000-0000-0000-000000000000"


@pytest.fixture
def operator_headers(
    create_user: CreateUser, authenticate_as: AuthenticateAs
) -> dict[str, str]:
    return authenticate_as(create_user(role=Role.OPERATOR))


@pytest.fixture
def mirante(create_condominium: CreateCondominium) -> Condominium:
    return create_condominium(name="Residencial Mirante")


def new_debtor(condominium: Condominium, **fields: Any) -> dict[str, Any]:
    return {
        "condominium_id": str(condominium.id),
        "name": "José Simão",
        "unit": "Bloco B 304",
        "phone": "(61) 91234-5678",
        **fields,
    }


def register(
    client: TestClient, headers: dict[str, str], payload: dict[str, Any]
) -> httpx.Response:
    response: httpx.Response = client.post("/debtors", json=payload, headers=headers)
    return response


class TestRegisterDebtor:
    def test_operator_registers_a_debtor(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        mirante: Condominium,
    ) -> None:
        """US13"""
        response = register(db_client, operator_headers, new_debtor(mirante))

        assert response.status_code == 201
        body = response.json()
        assert body["condominium_id"] == str(mirante.id)
        assert body["name"] == "José Simão"
        assert body["phone"] == "61912345678"

    def test_similar_debtor_is_reported_instead_of_registered(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        mirante: Condominium,
        create_debtor: CreateDebtor,
    ) -> None:
        """US13-CA01"""
        registered = create_debtor(mirante, name="Jose Simao", unit="Torre A 101")

        response = register(db_client, operator_headers, new_debtor(mirante))

        assert response.status_code == 409
        body = response.json()
        assert body["detail"].startswith("Já existe devedor com dados parecidos")
        assert [debtor["id"] for debtor in body["similar_debtors"]] == [
            str(registered.id)
        ]

    def test_similar_debtor_is_registered_when_the_user_confirms(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        mirante: Condominium,
        create_debtor: CreateDebtor,
    ) -> None:
        """US13-CA01"""
        create_debtor(mirante, name="José Simão")

        response = register(
            db_client, operator_headers, new_debtor(mirante, confirm_duplicate=True)
        )

        assert response.status_code == 201

    def test_same_debtor_in_another_condominium_is_not_similar(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        mirante: Condominium,
        create_condominium: CreateCondominium,
        create_debtor: CreateDebtor,
    ) -> None:
        create_debtor(create_condominium(name="Cond. Lake View"))

        response = register(db_client, operator_headers, new_debtor(mirante))

        assert response.status_code == 201

    def test_debtor_without_phone_and_email_is_refused(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        mirante: Condominium,
    ) -> None:
        response = register(
            db_client, operator_headers, new_debtor(mirante, phone=None)
        )

        assert response.status_code == 422
        assert response.json()["detail"] == "Informe o telefone ou o e-mail do devedor."

    def test_unknown_condominium_is_not_found(
        self, db_client: TestClient, operator_headers: dict[str, str]
    ) -> None:
        payload = {
            "condominium_id": UNKNOWN_ID,
            "name": "José",
            "unit": "101",
            "phone": "61912345678",
        }

        response = register(db_client, operator_headers, payload)

        assert response.status_code == 404

    def test_client_user_is_refused(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
        mirante: Condominium,
    ) -> None:
        headers = authenticate_as(create_user(role=Role.CLIENT))

        assert register(db_client, headers, new_debtor(mirante)).status_code == 403


class TestSearchDebtors:
    def test_search_by_name_or_unit_within_a_condominium(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        mirante: Condominium,
        create_condominium: CreateCondominium,
        create_debtor: CreateDebtor,
    ) -> None:
        create_debtor(mirante, name="José Simão", unit="Bloco B 304")
        create_debtor(mirante, name="Maria Souza", unit="Torre A 101")
        create_debtor(create_condominium(name="Outro"), name="José Lima", unit="1")

        def names_found(params: dict[str, str]) -> list[str]:
            response = db_client.get(
                "/debtors", params=params, headers=operator_headers
            )
            return [debtor["name"] for debtor in response.json()]

        assert names_found({"search": "jos"}) == ["José Lima", "José Simão"]
        assert names_found({"condominium_id": str(mirante.id), "search": "jos"}) == [
            "José Simão"
        ]
        assert names_found({"search": "torre a"}) == ["Maria Souza"]

    def test_get_unknown_debtor_is_not_found(
        self, db_client: TestClient, operator_headers: dict[str, str]
    ) -> None:
        response = db_client.get(f"/debtors/{UNKNOWN_ID}", headers=operator_headers)

        assert response.status_code == 404
        assert response.json()["detail"] == "Devedor não encontrado."


class TestUpdateDebtor:
    def test_contact_data_can_be_updated(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        mirante: Condominium,
        create_debtor: CreateDebtor,
    ) -> None:
        debtor = create_debtor(mirante)

        response = db_client.patch(
            f"/debtors/{debtor.id}",
            json={"email": "jose@example.com", "phone": None},
            headers=operator_headers,
        )

        assert response.status_code == 200
        assert response.json()["email"] == "jose@example.com"
        assert response.json()["phone"] is None

    def test_removing_the_only_contact_is_refused(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        mirante: Condominium,
        create_debtor: CreateDebtor,
    ) -> None:
        debtor = create_debtor(mirante, email=None)

        response = db_client.patch(
            f"/debtors/{debtor.id}", json={"phone": None}, headers=operator_headers
        )

        assert response.status_code == 422
