import uuid
from collections.abc import Mapping
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from advocondo.acordos.models import AgreementEditField, AgreementEditLog
from advocondo.condominios.models import Condominium
from advocondo.devedores.models import Debtor
from advocondo.parcelas.models import Installment
from advocondo.users.models import Role, User, UserStatus
from tests.fixtures.auth import AuthenticateAs
from tests.fixtures.condominios import CreateCondominium
from tests.fixtures.devedores import CreateDebtor
from tests.fixtures.users import CreateUser
from tests.support.clock import FrozenClock

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


@pytest.fixture
def agreement_id(
    db_client: TestClient,
    operator_headers: dict[str, str],
    mirante: Condominium,
    jose: Debtor,
) -> str:
    created = register(db_client, operator_headers, new_agreement(mirante.id, jose.id))
    value: str = created.json()["id"]
    return value


@pytest.fixture
def lawyer(create_user: CreateUser) -> User:
    return create_user(
        email="marina@example.com",
        name="Marina Dias",
        role=Role.OPERATOR,
        is_lawyer=True,
        oab_number="123456/DF",
    )


def new_agreement(
    condominium_id: object, debtor_id: object, **fields: Any
) -> dict[str, Any]:
    return {
        "condominium_id": str(condominium_id),
        "debtor_id": str(debtor_id),
        "total_amount": "5500.00",
        "installment_count": 10,
        "first_due_date": "2026-01-31",
        "fee_percentage": "10",
        **fields,
    }


def register(
    client: TestClient, headers: dict[str, str], payload: dict[str, Any]
) -> httpx.Response:
    response: httpx.Response = client.post("/agreements", json=payload, headers=headers)
    return response


def assign_lawyer(
    client: TestClient, headers: dict[str, str], agreement_id: str, lawyer_id: object
) -> httpx.Response:
    response: httpx.Response = client.put(
        f"/agreements/{agreement_id}/responsible-lawyer",
        json={"lawyer_id": str(lawyer_id)},
        headers=headers,
    )
    return response


def update_agreement(
    client: TestClient,
    headers: dict[str, str],
    agreement_id: str,
    payload: Mapping[str, object],
) -> httpx.Response:
    response: httpx.Response = client.patch(
        f"/agreements/{agreement_id}", json=payload, headers=headers
    )
    return response


def installments_of(db_session: Session, agreement_id: str) -> list[Installment]:
    return list(
        db_session.scalars(
            select(Installment)
            .where(Installment.agreement_id == uuid.UUID(agreement_id))
            .order_by(Installment.number)
        )
    )


def pay_installments(db_session: Session, agreement_id: str, count: int) -> None:
    for installment in installments_of(db_session, agreement_id)[:count]:
        installment.paid_amount = installment.amount
        installment.payment_date = date(2026, 2, 1)
    db_session.flush()


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

    def test_money_is_returned_with_two_decimal_places(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        mirante: Condominium,
        jose: Debtor,
    ) -> None:
        response = register(
            db_client,
            operator_headers,
            new_agreement(mirante.id, jose.id, total_amount="5500"),
        )

        assert response.status_code == 201
        assert response.json()["total_amount"] == "5500.00"

    def test_installments_are_generated_with_the_agreement(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        mirante: Condominium,
        jose: Debtor,
    ) -> None:
        """US17-CA01"""
        response = register(
            db_client, operator_headers, new_agreement(mirante.id, jose.id)
        )

        assert response.json()["installment_count"] == 10

    def test_installment_below_one_cent_is_refused(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        mirante: Condominium,
        jose: Debtor,
    ) -> None:
        payload = new_agreement(mirante.id, jose.id, total_amount="0.05")

        response = register(db_client, operator_headers, payload)

        assert response.status_code == 422
        assert response.json()["detail"].startswith("Cada parcela precisa ter")

    @pytest.mark.parametrize(
        ("fee", "expected_amount", "expected_percentage"),
        [
            pytest.param({"fee_percentage": "10"}, "550.00", "10.00", id="percentage"),
            pytest.param(
                {"fee_percentage": None, "fee_amount": "600"},
                "600.00",
                None,
                id="amount",
            ),
        ],
    )
    def test_fee_is_given_as_percentage_or_amount(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        mirante: Condominium,
        jose: Debtor,
        fee: dict[str, str | None],
        expected_amount: str,
        expected_percentage: str | None,
    ) -> None:
        """US16-CA01"""
        payload = new_agreement(mirante.id, jose.id, **fee)

        body = register(db_client, operator_headers, payload).json()

        assert body["fee_amount"] == expected_amount
        assert body["fee_percentage"] == expected_percentage

    def test_fee_above_the_total_is_refused(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        mirante: Condominium,
        jose: Debtor,
    ) -> None:
        payload = new_agreement(
            mirante.id, jose.id, fee_percentage=None, fee_amount="5500.01"
        )

        response = register(db_client, operator_headers, payload)

        assert response.status_code == 422
        assert response.json()["detail"] == (
            "Os honorários não podem ser maiores que o valor total do acordo."
        )

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


class TestSearchAgreements:
    def test_registered_agreement_appears_in_the_active_list(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        mirante: Condominium,
        jose: Debtor,
    ) -> None:
        """US15-CA01"""
        agreement_id = register(
            db_client, operator_headers, new_agreement(mirante.id, jose.id)
        ).json()["id"]

        response = db_client.get(
            "/agreements", params={"status": "active"}, headers=operator_headers
        )

        assert [agreement["id"] for agreement in response.json()] == [agreement_id]

    def test_agreements_can_be_filtered_by_condominium(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        mirante: Condominium,
        jose: Debtor,
        create_condominium: CreateCondominium,
        create_debtor: CreateDebtor,
    ) -> None:
        """US15-CA03: what the Client of a condominium will see (US37)."""
        lake_view = create_condominium(name="Cond. Lake View")
        maria = create_debtor(lake_view, name="Maria Souza")
        register(db_client, operator_headers, new_agreement(mirante.id, jose.id))
        register(db_client, operator_headers, new_agreement(lake_view.id, maria.id))

        response = db_client.get(
            "/agreements",
            params={"condominium_id": str(lake_view.id)},
            headers=operator_headers,
        )

        assert [agreement["debtor"]["name"] for agreement in response.json()] == [
            "Maria Souza"
        ]

    def test_agreements_can_be_filtered_by_debtor(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        mirante: Condominium,
        jose: Debtor,
        create_debtor: CreateDebtor,
    ) -> None:
        maria = create_debtor(mirante, name="Maria Souza", unit="Bloco A 101")
        register(db_client, operator_headers, new_agreement(mirante.id, jose.id))
        register(db_client, operator_headers, new_agreement(mirante.id, maria.id))

        response = db_client.get(
            "/agreements",
            params={"debtor_id": str(maria.id)},
            headers=operator_headers,
        )

        assert [agreement["debtor"]["name"] for agreement in response.json()] == [
            "Maria Souza"
        ]

    def test_unknown_status_is_refused(
        self, db_client: TestClient, operator_headers: dict[str, str]
    ) -> None:
        response = db_client.get(
            "/agreements", params={"status": "archived"}, headers=operator_headers
        )

        assert response.status_code == 422


class TestGetAgreement:
    def test_returns_the_agreement(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        mirante: Condominium,
        jose: Debtor,
    ) -> None:
        agreement_id = register(
            db_client, operator_headers, new_agreement(mirante.id, jose.id)
        ).json()["id"]

        response = db_client.get(
            f"/agreements/{agreement_id}", headers=operator_headers
        )

        assert response.status_code == 200
        assert response.json()["total_amount"] == "5500.00"

    def test_unknown_agreement_is_not_found(
        self, db_client: TestClient, operator_headers: dict[str, str]
    ) -> None:
        response = db_client.get(f"/agreements/{UNKNOWN_ID}", headers=operator_headers)

        assert response.status_code == 404
        assert response.json()["detail"] == "Acordo não encontrado."


class TestAssignLawyer:
    def test_agreement_is_assigned_to_a_lawyer(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        mirante: Condominium,
        jose: Debtor,
        lawyer: User,
    ) -> None:
        """US18-CA01"""
        agreement_id = register(
            db_client, operator_headers, new_agreement(mirante.id, jose.id)
        ).json()["id"]

        response = assign_lawyer(db_client, operator_headers, agreement_id, lawyer.id)

        assert response.status_code == 200
        assert response.json()["responsible_lawyer"] == {
            "id": str(lawyer.id),
            "name": "Marina Dias",
            "oab_number": "123456/DF",
        }
        fetched = db_client.get(f"/agreements/{agreement_id}", headers=operator_headers)
        assert fetched.json()["responsible_lawyer"]["name"] == "Marina Dias"

    @pytest.mark.parametrize(
        ("is_lawyer", "status"),
        [
            pytest.param(False, UserStatus.ACTIVE, id="not-a-lawyer"),
            pytest.param(True, UserStatus.PENDING, id="pending-lawyer"),
            pytest.param(True, UserStatus.INACTIVE, id="inactive-lawyer"),
        ],
    )
    def test_only_active_lawyers_can_be_chosen(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        operator_headers: dict[str, str],
        mirante: Condominium,
        jose: Debtor,
        is_lawyer: bool,
        status: UserStatus,
    ) -> None:
        """US18-CA01"""
        candidate = create_user(
            email="candidato@example.com",
            role=Role.OPERATOR,
            is_lawyer=is_lawyer,
            oab_number="654321/SP" if is_lawyer else None,
            status=status,
        )
        agreement_id = register(
            db_client, operator_headers, new_agreement(mirante.id, jose.id)
        ).json()["id"]

        response = assign_lawyer(
            db_client, operator_headers, agreement_id, candidate.id
        )

        assert response.status_code == 422
        assert response.json()["detail"] == (
            "O responsável precisa ser um advogado ativo, com OAB cadastrada."
        )

    def test_unknown_lawyer_and_unknown_agreement_are_not_found(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        mirante: Condominium,
        jose: Debtor,
        lawyer: User,
    ) -> None:
        """US18-CA01"""
        agreement_id = register(
            db_client, operator_headers, new_agreement(mirante.id, jose.id)
        ).json()["id"]

        unknown_lawyer = assign_lawyer(
            db_client, operator_headers, agreement_id, UNKNOWN_ID
        )
        unknown_agreement = assign_lawyer(
            db_client, operator_headers, UNKNOWN_ID, lawyer.id
        )

        assert unknown_lawyer.status_code == 404
        assert unknown_lawyer.json()["detail"] == "Advogado não encontrado."
        assert unknown_agreement.status_code == 404
        assert unknown_agreement.json()["detail"] == "Acordo não encontrado."

    @pytest.mark.parametrize(
        ("caller_role", "expected_status"),
        [
            pytest.param(Role.ADMIN, 200, id="admin"),
            pytest.param(Role.OPERATOR, 200, id="operator"),
            pytest.param(Role.CLIENT, 403, id="client"),
        ],
    )
    def test_administrators_and_operators_can_assign_lawyers(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
        operator_headers: dict[str, str],
        mirante: Condominium,
        jose: Debtor,
        lawyer: User,
        caller_role: Role,
        expected_status: int,
    ) -> None:
        """US18-CA01"""
        agreement_id = register(
            db_client, operator_headers, new_agreement(mirante.id, jose.id)
        ).json()["id"]
        caller = create_user(email="chamador@example.com", role=caller_role)

        response = assign_lawyer(
            db_client, authenticate_as(caller), agreement_id, lawyer.id
        )

        assert response.status_code == expected_status

    def test_request_without_a_token_is_refused(
        self, db_client: TestClient, lawyer: User
    ) -> None:
        """US18-CA01"""
        response = assign_lawyer(db_client, {}, UNKNOWN_ID, lawyer.id)

        assert response.status_code == 401


class TestLawyerHistory:
    def test_reassigning_keeps_the_history(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
        mirante: Condominium,
        jose: Debtor,
        lawyer: User,
        clock: FrozenClock,
    ) -> None:
        """US18-CA02"""
        operator = create_user(
            email="beto@example.com", name="Beto Lima", role=Role.OPERATOR
        )
        headers = authenticate_as(operator)
        rui = create_user(
            email="rui@example.com",
            name="Rui Alves",
            role=Role.OPERATOR,
            is_lawyer=True,
            oab_number="777777/GO",
        )
        agreement_id = register(
            db_client, headers, new_agreement(mirante.id, jose.id)
        ).json()["id"]
        assign_lawyer(db_client, headers, agreement_id, lawyer.id)
        clock.advance(timedelta(minutes=5))
        assign_lawyer(db_client, headers, agreement_id, rui.id)

        response = db_client.get(
            f"/agreements/{agreement_id}/lawyer-history", headers=headers
        )

        history = response.json()
        assert response.status_code == 200
        assert [entry["new_lawyer"]["name"] for entry in history] == [
            "Marina Dias",
            "Rui Alves",
        ]
        assert history[0]["previous_lawyer"] is None
        assert history[1]["previous_lawyer"]["name"] == "Marina Dias"
        assert history[1]["assigned_by"] == {
            "id": str(operator.id),
            "name": "Beto Lima",
        }
        assert history[0]["assigned_at"] < history[1]["assigned_at"]

    def test_assigning_the_same_lawyer_again_adds_nothing_to_the_history(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        mirante: Condominium,
        jose: Debtor,
        lawyer: User,
    ) -> None:
        """US18-CA02"""
        agreement_id = register(
            db_client, operator_headers, new_agreement(mirante.id, jose.id)
        ).json()["id"]
        assign_lawyer(db_client, operator_headers, agreement_id, lawyer.id)
        assign_lawyer(db_client, operator_headers, agreement_id, lawyer.id)

        response = db_client.get(
            f"/agreements/{agreement_id}/lawyer-history", headers=operator_headers
        )

        assert len(response.json()) == 1

    def test_unknown_agreement_is_not_found(
        self, db_client: TestClient, operator_headers: dict[str, str]
    ) -> None:
        """US18-CA02"""
        response = db_client.get(
            f"/agreements/{UNKNOWN_ID}/lawyer-history", headers=operator_headers
        )

        assert response.status_code == 404


class TestAgreementsOfALawyer:
    def test_lawyer_lists_only_the_agreements_under_their_responsibility(
        self,
        db_client: TestClient,
        create_debtor: CreateDebtor,
        authenticate_as: AuthenticateAs,
        operator_headers: dict[str, str],
        mirante: Condominium,
        jose: Debtor,
        lawyer: User,
    ) -> None:
        """US18-CA03"""
        carla = create_debtor(mirante, name="Carla Nunes", unit="Bloco A 101")
        mine = register(
            db_client, operator_headers, new_agreement(mirante.id, jose.id)
        ).json()["id"]
        register(db_client, operator_headers, new_agreement(mirante.id, carla.id))
        assign_lawyer(db_client, operator_headers, mine, lawyer.id)

        response = db_client.get(
            "/agreements",
            params={"responsible_lawyer_id": str(lawyer.id)},
            headers=authenticate_as(lawyer),
        )

        assert response.status_code == 200
        assert [item["id"] for item in response.json()] == [mine]


class TestUpdateAgreement:
    def test_total_amount_is_renegotiated_and_open_installments_follow(
        self,
        db_client: TestClient,
        db_session: Session,
        operator_headers: dict[str, str],
        agreement_id: str,
    ) -> None:
        """US19"""
        response = update_agreement(
            db_client, operator_headers, agreement_id, {"total_amount": "4000.00"}
        )

        body = response.json()
        installments = installments_of(db_session, agreement_id)
        assert response.status_code == 200
        assert body["total_amount"] == "4000.00"
        assert body["fee_amount"] == "400.00"
        assert body["fee_percentage"] == "10.00"
        assert [item.amount for item in installments] == [Decimal("400.00")] * 10
        assert [item.fee_amount for item in installments] == [Decimal("40.00")] * 10

    def test_fee_can_be_typed_in_reais(
        self,
        db_client: TestClient,
        db_session: Session,
        operator_headers: dict[str, str],
        agreement_id: str,
    ) -> None:
        """US19"""
        response = update_agreement(
            db_client, operator_headers, agreement_id, {"fee_amount": "300.00"}
        )

        assert response.status_code == 200
        assert response.json()["fee_amount"] == "300.00"
        assert response.json()["fee_percentage"] is None
        installments = installments_of(db_session, agreement_id)
        assert [item.fee_amount for item in installments] == [Decimal("30.00")] * 10

    def test_debtor_can_be_corrected(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        create_debtor: CreateDebtor,
        mirante: Condominium,
        agreement_id: str,
    ) -> None:
        """US19"""
        carla = create_debtor(mirante, name="Carla Nunes", unit="Bloco A 101")

        response = update_agreement(
            db_client,
            operator_headers,
            agreement_id,
            {"debtor_id": str(carla.id)},
        )

        assert response.status_code == 200
        assert response.json()["debtor"]["name"] == "Carla Nunes"

    def test_debtor_of_another_condominium_is_refused(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        create_condominium: CreateCondominium,
        create_debtor: CreateDebtor,
        agreement_id: str,
    ) -> None:
        """US19"""
        lake_view = create_condominium(name="Cond. Lake View")
        stranger = create_debtor(lake_view, name="Rui Alves", unit="Casa 7")

        response = update_agreement(
            db_client,
            operator_headers,
            agreement_id,
            {"debtor_id": str(stranger.id)},
        )

        assert response.status_code == 422

    def test_unknown_debtor_and_unknown_agreement_are_not_found(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        agreement_id: str,
    ) -> None:
        """US19"""
        unknown_debtor = update_agreement(
            db_client, operator_headers, agreement_id, {"debtor_id": str(uuid.uuid4())}
        )
        unknown_agreement = update_agreement(
            db_client,
            operator_headers,
            str(uuid.uuid4()),
            {"total_amount": "4000.00"},
        )

        assert unknown_debtor.status_code == 404
        assert unknown_agreement.status_code == 404

    def test_request_without_a_token_is_refused(
        self, db_client: TestClient, agreement_id: str
    ) -> None:
        """US19"""
        response = update_agreement(
            db_client, {}, agreement_id, {"total_amount": "4000.00"}
        )

        assert response.status_code == 401

    def test_client_cannot_edit_an_agreement(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
        agreement_id: str,
    ) -> None:
        """US19"""
        client_user = create_user(email="sindico@example.com", role=Role.CLIENT)

        response = update_agreement(
            db_client,
            authenticate_as(client_user),
            agreement_id,
            {"total_amount": "4000.00"},
        )

        assert response.status_code == 403

    def test_nothing_changed_writes_nothing_and_asks_for_no_confirmation(
        self,
        db_client: TestClient,
        db_session: Session,
        operator_headers: dict[str, str],
        jose: Debtor,
        agreement_id: str,
    ) -> None:
        """US19-CA01"""
        pay_installments(db_session, agreement_id, 1)
        payloads = [
            {"total_amount": "5500.00"},
            {"fee_amount": "550.00"},
            {"debtor_id": str(jose.id)},
        ]

        statuses = [
            update_agreement(
                db_client, operator_headers, agreement_id, payload
            ).status_code
            for payload in payloads
        ]

        logs = db_session.scalars(select(AgreementEditLog)).all()
        assert statuses == [200, 200, 200]
        assert logs == []


class TestPaidInstallments:
    def test_agreement_with_paid_installments_needs_confirmation(
        self,
        db_client: TestClient,
        db_session: Session,
        operator_headers: dict[str, str],
        agreement_id: str,
    ) -> None:
        """US19-CA01"""
        pay_installments(db_session, agreement_id, 1)

        response = update_agreement(
            db_client, operator_headers, agreement_id, {"total_amount": "4000.00"}
        )

        fetched = db_client.get(f"/agreements/{agreement_id}", headers=operator_headers)
        assert response.status_code == 409
        assert response.json()["detail"] == (
            "Este acordo já tem parcelas pagas. Confirme a alteração para continuar."
        )
        assert fetched.json()["total_amount"] == "5500.00"

    def test_confirmed_edit_leaves_the_paid_installments_alone(
        self,
        db_client: TestClient,
        db_session: Session,
        operator_headers: dict[str, str],
        agreement_id: str,
    ) -> None:
        """US19-CA01"""
        pay_installments(db_session, agreement_id, 1)

        response = update_agreement(
            db_client,
            operator_headers,
            agreement_id,
            {"total_amount": "4000.00", "confirm_paid_installments": True},
        )

        paid, *open_installments = installments_of(db_session, agreement_id)
        assert response.status_code == 200
        assert (paid.amount, paid.fee_amount) == (Decimal("550.00"), Decimal("55.00"))
        assert paid.payment_date == date(2026, 2, 1)
        assert sum(item.amount for item in open_installments) == Decimal("3450.00")
        assert sum(item.fee_amount for item in open_installments) == Decimal("345.00")

    @pytest.mark.parametrize(
        ("paid_count", "payload"),
        [
            pytest.param(1, {"total_amount": "500.00"}, id="total-below-what-was-paid"),
            pytest.param(
                10, {"total_amount": "4000.00"}, id="nothing-left-to-recalculate"
            ),
        ],
    )
    def test_confirmed_edit_that_cannot_be_recalculated_is_refused(
        self,
        db_client: TestClient,
        db_session: Session,
        operator_headers: dict[str, str],
        agreement_id: str,
        paid_count: int,
        payload: dict[str, object],
    ) -> None:
        """US19-CA01"""
        pay_installments(db_session, agreement_id, paid_count)

        response = update_agreement(
            db_client,
            operator_headers,
            agreement_id,
            {**payload, "confirm_paid_installments": True},
        )

        assert response.status_code == 422


class TestEditLog:
    def test_edit_is_logged_with_who_changed_it_and_when(
        self,
        db_client: TestClient,
        db_session: Session,
        create_user: CreateUser,
        create_debtor: CreateDebtor,
        authenticate_as: AuthenticateAs,
        mirante: Condominium,
        agreement_id: str,
        clock: FrozenClock,
    ) -> None:
        """US19-CA02"""
        ana = create_user(email="ana.edit@example.com", name="Ana", role=Role.OPERATOR)
        carla = create_debtor(mirante, name="Carla Nunes", unit="Bloco A 101")

        update_agreement(
            db_client,
            authenticate_as(ana),
            agreement_id,
            {"debtor_id": str(carla.id), "total_amount": "4000.00"},
        )

        logs = db_session.scalars(select(AgreementEditLog)).all()
        assert {log.field for log in logs} == {
            AgreementEditField.DEBTOR,
            AgreementEditField.TOTAL_AMOUNT,
            AgreementEditField.FEE_AMOUNT,
        }
        assert all(log.edited_by_id == ana.id for log in logs)
        assert all(log.edited_at == clock.now() for log in logs)
        assert all(log.had_paid_installments is False for log in logs)
        total = next(
            log for log in logs if log.field == AgreementEditField.TOTAL_AMOUNT
        )
        assert (total.old_value, total.new_value) == ("5500.00", "4000.00")

    def test_log_records_that_the_agreement_already_had_paid_installments(
        self,
        db_client: TestClient,
        db_session: Session,
        operator_headers: dict[str, str],
        agreement_id: str,
    ) -> None:
        """US19-CA02"""
        pay_installments(db_session, agreement_id, 1)

        update_agreement(
            db_client,
            operator_headers,
            agreement_id,
            {"total_amount": "4000.00", "confirm_paid_installments": True},
        )

        logs = db_session.scalars(select(AgreementEditLog)).all()
        assert logs != []
        assert all(log.had_paid_installments is True for log in logs)


def cancel(
    client: TestClient,
    headers: dict[str, str],
    agreement_id: object,
    **body: Any,
) -> httpx.Response:
    response: httpx.Response = client.post(
        f"/agreements/{agreement_id}/cancel", json=body, headers=headers
    )
    return response


def pay_first_installment(
    client: TestClient, headers: dict[str, str], agreement_id: str
) -> None:
    plan = client.get(f"/agreements/{agreement_id}/installments", headers=headers)
    response = client.post(
        f"/installments/{plan.json()[0]['id']}/payment",
        json={"payment_date": "2026-02-01"},
        headers=headers,
    )
    assert response.status_code == 200


class TestCancelAgreement:
    """US20. O relógio dos testes está em 2 de março de 2026, às 9h UTC."""

    @pytest.fixture
    def agreement_id(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        mirante: Condominium,
        jose: Debtor,
    ) -> str:
        """Acordo de R$ 5.500,00 em 10 parcelas, todas ainda sem pagamento."""
        agreement_id: str = register(
            db_client, operator_headers, new_agreement(mirante.id, jose.id)
        ).json()["id"]
        return agreement_id

    def test_open_installments_must_be_confirmed_first(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        agreement_id: str,
    ) -> None:
        response = cancel(db_client, operator_headers, agreement_id)

        assert response.status_code == 409
        assert response.json() == {
            "detail": (
                "Há 10 parcelas sem pagamento, somando R$ 5.500,00. "
                "Confirme para cancelar o acordo."
            )
        }
        fetched = db_client.get(f"/agreements/{agreement_id}", headers=operator_headers)
        assert fetched.json()["status"] == "active"

    def test_a_single_open_installment_is_written_in_the_singular(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        mirante: Condominium,
        jose: Debtor,
    ) -> None:
        agreement_id = register(
            db_client,
            operator_headers,
            new_agreement(mirante.id, jose.id, installment_count=1),
        ).json()["id"]

        response = cancel(db_client, operator_headers, agreement_id)

        assert response.json()["detail"] == (
            "Há 1 parcela sem pagamento, somando R$ 5.500,00. "
            "Confirme para cancelar o acordo."
        )

    def test_confirmed_cancellation_keeps_the_moment_and_the_reason(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        agreement_id: str,
    ) -> None:
        """US20"""
        response = cancel(
            db_client,
            operator_headers,
            agreement_id,
            reason="Devedor quebrou o acordo",
            confirm_open_installments=True,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "cancelled"
        assert body["cancelled_at"].startswith("2026-03-02T09:00:00")
        assert body["cancellation_reason"] == "Devedor quebrou o acordo"

    def test_reason_is_optional(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        agreement_id: str,
    ) -> None:
        response = cancel(
            db_client, operator_headers, agreement_id, confirm_open_installments=True
        )

        assert response.status_code == 200
        assert response.json()["cancellation_reason"] is None

    def test_agreement_fully_paid_needs_no_confirmation(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        mirante: Condominium,
        jose: Debtor,
    ) -> None:
        agreement_id = register(
            db_client,
            operator_headers,
            new_agreement(mirante.id, jose.id, installment_count=1),
        ).json()["id"]
        pay_first_installment(db_client, operator_headers, agreement_id)

        response = cancel(db_client, operator_headers, agreement_id)

        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"

    def test_only_the_installments_without_payment_are_counted(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        agreement_id: str,
    ) -> None:
        pay_first_installment(db_client, operator_headers, agreement_id)

        response = cancel(db_client, operator_headers, agreement_id)

        assert response.json()["detail"] == (
            "Há 9 parcelas sem pagamento, somando R$ 4.950,00. "
            "Confirme para cancelar o acordo."
        )

    def test_cancelled_agreement_cannot_be_cancelled_again(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        agreement_id: str,
    ) -> None:
        cancel(
            db_client, operator_headers, agreement_id, confirm_open_installments=True
        )

        response = cancel(
            db_client, operator_headers, agreement_id, confirm_open_installments=True
        )

        assert response.status_code == 422
        assert response.json() == {"detail": "O acordo já está cancelado."}

    def test_unknown_agreement_is_not_found(
        self, db_client: TestClient, operator_headers: dict[str, str]
    ) -> None:
        response = cancel(db_client, operator_headers, UNKNOWN_ID)

        assert response.status_code == 404

    @pytest.mark.parametrize(
        "body",
        [
            pytest.param({"reason": "x" * 501}, id="reason-too-long"),
            pytest.param({"confirm_open_installments": "talvez"}, id="not-a-boolean"),
            pytest.param({"status": "active"}, id="unknown-field"),
        ],
    )
    def test_invalid_request_is_refused(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        agreement_id: str,
        body: dict[str, Any],
    ) -> None:
        response = cancel(db_client, operator_headers, agreement_id, **body)

        assert response.status_code == 422

    def test_client_user_cannot_cancel(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
        agreement_id: str,
    ) -> None:
        headers = authenticate_as(
            create_user(email="sindico@example.com", role=Role.CLIENT)
        )

        response = cancel(
            db_client, headers, agreement_id, confirm_open_installments=True
        )

        assert response.status_code == 403

    def test_cancelling_requires_a_session(
        self, db_client: TestClient, agreement_id: str
    ) -> None:
        response = db_client.post(f"/agreements/{agreement_id}/cancel", json={})

        assert response.status_code == 401

    def test_cancelled_agreement_leaves_the_active_list(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        agreement_id: str,
    ) -> None:
        """US20"""
        cancel(
            db_client, operator_headers, agreement_id, confirm_open_installments=True
        )

        active = db_client.get(
            "/agreements", params={"status": "active"}, headers=operator_headers
        )
        cancelled = db_client.get(
            "/agreements", params={"status": "cancelled"}, headers=operator_headers
        )

        assert active.json() == []
        assert [item["id"] for item in cancelled.json()] == [agreement_id]

    def test_lawyer_cannot_be_changed_on_a_cancelled_agreement(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        agreement_id: str,
        lawyer: User,
    ) -> None:
        cancel(
            db_client, operator_headers, agreement_id, confirm_open_installments=True
        )

        response = assign_lawyer(db_client, operator_headers, agreement_id, lawyer.id)

        assert response.status_code == 422
        assert response.json() == {
            "detail": "Acordo cancelado não aceita esta operação."
        }

    def test_cancelled_agreement_cannot_be_edited(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        agreement_id: str,
    ) -> None:
        """US19 e US20: o cancelado sai da cobrança, então não é renegociado."""
        cancel(
            db_client, operator_headers, agreement_id, confirm_open_installments=True
        )

        response = update_agreement(
            db_client, operator_headers, agreement_id, {"total_amount": "4000.00"}
        )

        assert response.status_code == 422
        assert response.json() == {
            "detail": "Acordo cancelado não aceita esta operação."
        }
