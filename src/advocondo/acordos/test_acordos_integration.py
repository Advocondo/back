from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from advocondo.condominios.models import Condominium
from advocondo.devedores.models import Debtor
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


@pytest.fixture
def jose(mirante: Condominium, create_debtor: CreateDebtor) -> Debtor:
    return create_debtor(mirante, name="José Simão", unit="Bloco B 304")


def new_agreement(
    condominium_id: object, debtor_id: object, **fields: Any
) -> dict[str, Any]:
    return {
        "condominium_id": str(condominium_id),
        "debtor_id": str(debtor_id),
        "total_amount": "5500.00",
        **fields,
    }


def register(
    client: TestClient, headers: dict[str, str], payload: dict[str, Any]
) -> httpx.Response:
    response: httpx.Response = client.post("/agreements", json=payload, headers=headers)
    return response


class TestRegisterAgreement:
    def test_agreement_is_registered_active_and_linked_to_the_condominium(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        mirante: Condominium,
        jose: Debtor,
    ) -> None:
        """US15-CA01 and US15-CA03"""
        response = register(
            db_client, operator_headers, new_agreement(mirante.id, jose.id)
        )

        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "active"
        assert body["total_amount"] == "5500.00"
        assert body["condominium"] == {
            "id": str(mirante.id),
            "name": "Residencial Mirante",
        }
        assert body["debtor"]["name"] == "José Simão"

    def test_debtor_of_another_condominium_is_refused(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        jose: Debtor,
        create_condominium: CreateCondominium,
    ) -> None:
        other = create_condominium(name="Cond. Lake View")

        response = register(
            db_client, operator_headers, new_agreement(other.id, jose.id)
        )

        assert response.status_code == 422
        assert response.json()["detail"] == (
            "O devedor informado não pertence a este condomínio."
        )

    @pytest.mark.parametrize(
        ("unknown", "message"),
        [
            pytest.param("condominium", "Condomínio não encontrado.", id="condominium"),
            pytest.param("debtor", "Devedor não encontrado.", id="debtor"),
        ],
    )
    def test_unknown_condominium_or_debtor_is_not_found(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        mirante: Condominium,
        jose: Debtor,
        unknown: str,
        message: str,
    ) -> None:
        """US12-CA01: an agreement needs a registered condominium."""
        condominium_id = UNKNOWN_ID if unknown == "condominium" else mirante.id
        debtor_id = UNKNOWN_ID if unknown == "debtor" else jose.id

        response = register(
            db_client, operator_headers, new_agreement(condominium_id, debtor_id)
        )

        assert response.status_code == 404
        assert response.json()["detail"] == message

    def test_missing_total_amount_is_refused(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        mirante: Condominium,
        jose: Debtor,
    ) -> None:
        """US15-CA02"""
        payload = new_agreement(mirante.id, jose.id)
        del payload["total_amount"]

        assert register(db_client, operator_headers, payload).status_code == 422

    def test_client_user_is_refused(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
        mirante: Condominium,
        jose: Debtor,
    ) -> None:
        headers = authenticate_as(create_user(role=Role.CLIENT))

        response = register(db_client, headers, new_agreement(mirante.id, jose.id))

        assert response.status_code == 403
