import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from advocondo.condominios.models import Condominium
from advocondo.devedores.models import Debtor
from advocondo.parcelas.models import Installment
from advocondo.users.models import Role
from tests.fixtures.auth import AuthenticateAs
from tests.fixtures.condominios import CreateCondominium
from tests.fixtures.devedores import CreateDebtor
from tests.fixtures.metas import CreateGoal
from tests.fixtures.users import CreateUser


def close_agreement(
    client: TestClient,
    headers: dict[str, str],
    condominium: Condominium,
    debtor: Debtor,
) -> str:
    """Cadastra um acordo pela API: 10 parcelas de R$ 550,00, com R$ 55,00 de honorários cada."""
    response = client.post(
        "/agreements",
        json={
            "condominium_id": str(condominium.id),
            "debtor_id": str(debtor.id),
            "total_amount": "5500.00",
            "installment_count": 10,
            "first_due_date": "2026-01-31",
            "fee_percentage": "10",
        },
        headers=headers,
    )
    agreement_id: str = response.json()["id"]
    return agreement_id


def pay_installments(
    db_session: Session, agreement_id: str, payment_dates: list[date]
) -> None:
    """Dá baixa nas primeiras parcelas do acordo, uma data para cada."""
    installments = db_session.scalars(
        select(Installment)
        .where(Installment.agreement_id == uuid.UUID(agreement_id))
        .order_by(Installment.number)
    ).all()
    for installment, payment_date in zip(installments, payment_dates, strict=False):
        installment.receive(installment.amount, payment_date)
    db_session.flush()


class TestDefineGoal:
    def test_administrator_defines_the_goal_of_an_operator(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
    ) -> None:
        """US36-CA01"""
        admin = create_user(email="admin@example.com", role=Role.ADMIN)
        operator = create_user(email="operador@example.com", role=Role.OPERATOR)

        response = db_client.put(
            f"/users/{operator.id}/goals/2026/3",
            json={"target_amount": "5000.00"},
            headers=authenticate_as(admin),
        )

        assert response.status_code == 200
        body = response.json()
        assert body["user_id"] == str(operator.id)
        assert (body["year"], body["month"]) == (2026, 3)
        assert body["target_amount"] == "5000.00"

    def test_defining_again_changes_the_amount_without_a_second_goal(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
    ) -> None:
        """US36-CA01"""
        admin = create_user(email="admin@example.com", role=Role.ADMIN)
        operator = create_user(email="operador@example.com", role=Role.OPERATOR)
        url = f"/users/{operator.id}/goals/2026/3"
        headers = authenticate_as(admin)

        first = db_client.put(url, json={"target_amount": "5000.00"}, headers=headers)
        second = db_client.put(url, json={"target_amount": "6500.50"}, headers=headers)

        assert second.status_code == 200
        assert second.json()["id"] == first.json()["id"]
        assert second.json()["target_amount"] == "6500.50"

    @pytest.mark.parametrize(
        ("caller_role", "expected_status"),
        [
            pytest.param(Role.ADMIN, 200, id="admin"),
            pytest.param(Role.OPERATOR, 403, id="operator"),
            pytest.param(Role.CLIENT, 403, id="client"),
        ],
    )
    def test_only_administrators_can_define_goals(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
        caller_role: Role,
        expected_status: int,
    ) -> None:
        """US36-CA01"""
        caller = create_user(email="chamador@example.com", role=caller_role)
        target = create_user(email="alvo@example.com", role=Role.OPERATOR)

        response = db_client.put(
            f"/users/{target.id}/goals/2026/3",
            json={"target_amount": "5000.00"},
            headers=authenticate_as(caller),
        )

        assert response.status_code == expected_status

    def test_request_without_a_token_is_refused(
        self, db_client: TestClient, create_user: CreateUser
    ) -> None:
        """US36-CA01"""
        operator = create_user(role=Role.OPERATOR)

        response = db_client.put(
            f"/users/{operator.id}/goals/2026/3", json={"target_amount": "5000.00"}
        )

        assert response.status_code == 401

    @pytest.mark.parametrize(
        "role",
        [pytest.param(Role.ADMIN, id="admin"), pytest.param(Role.CLIENT, id="client")],
    )
    def test_only_operators_can_have_a_goal(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
        role: Role,
    ) -> None:
        """US36-CA01"""
        admin = create_user(email="admin@example.com", role=Role.ADMIN)
        target = create_user(email="alvo@example.com", role=role)

        response = db_client.put(
            f"/users/{target.id}/goals/2026/3",
            json={"target_amount": "5000.00"},
            headers=authenticate_as(admin),
        )

        assert response.status_code == 422
        assert (
            response.json()["detail"]
            == "Só membros da Equipe Operacional podem ter meta."
        )

    def test_unknown_collaborator_is_not_found(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
    ) -> None:
        """US36-CA01"""
        admin = create_user(role=Role.ADMIN)

        response = db_client.put(
            f"/users/{uuid.uuid4()}/goals/2026/3",
            json={"target_amount": "5000.00"},
            headers=authenticate_as(admin),
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Colaborador não encontrado."

    @pytest.mark.parametrize(
        ("period", "body"),
        [
            pytest.param("2026/0", {"target_amount": "5000.00"}, id="month-zero"),
            pytest.param("2026/13", {"target_amount": "5000.00"}, id="month-thirteen"),
            pytest.param("1999/3", {"target_amount": "5000.00"}, id="year-too-old"),
            pytest.param("2101/3", {"target_amount": "5000.00"}, id="year-too-far"),
            pytest.param("2026/3", {"target_amount": "0"}, id="zero-amount"),
            pytest.param("2026/3", {"target_amount": "-5"}, id="negative-amount"),
            pytest.param("2026/3", {}, id="missing-amount"),
        ],
    )
    def test_invalid_input_is_refused(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
        period: str,
        body: dict[str, str],
    ) -> None:
        """US36-CA01"""
        admin = create_user(email="admin@example.com", role=Role.ADMIN)
        operator = create_user(email="operador@example.com", role=Role.OPERATOR)

        response = db_client.put(
            f"/users/{operator.id}/goals/{period}",
            json=body,
            headers=authenticate_as(admin),
        )

        assert response.status_code == 422


class TestOwnGoal:
    def test_operator_sees_only_the_own_goal(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        create_goal: CreateGoal,
        authenticate_as: AuthenticateAs,
    ) -> None:
        """US36-CA02"""
        ana = create_user(email="ana@example.com", name="Ana", role=Role.OPERATOR)
        rui = create_user(email="rui@example.com", name="Rui", role=Role.OPERATOR)
        create_goal(ana, target_amount=Decimal("5000.00"))
        create_goal(rui, target_amount=Decimal("8000.00"))

        response = db_client.get(
            "/goals/me",
            params={"year": 2026, "month": 3},
            headers=authenticate_as(ana),
        )

        assert response.status_code == 200
        assert response.json()["user_id"] == str(ana.id)
        assert response.json()["target_amount"] == "5000.00"

    def test_month_without_a_goal_is_not_found(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        create_goal: CreateGoal,
        authenticate_as: AuthenticateAs,
    ) -> None:
        """US36-CA02"""
        ana = create_user(role=Role.OPERATOR)
        create_goal(ana, month=3)

        response = db_client.get(
            "/goals/me",
            params={"year": 2026, "month": 4},
            headers=authenticate_as(ana),
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Meta não encontrada."

    def test_request_without_a_token_is_refused(self, db_client: TestClient) -> None:
        """US36-CA02"""
        response = db_client.get("/goals/me", params={"year": 2026, "month": 3})

        assert response.status_code == 401

    @pytest.mark.parametrize(
        "params",
        [
            pytest.param({"month": 3}, id="missing-year"),
            pytest.param({"year": 2026}, id="missing-month"),
            pytest.param({"year": 2026, "month": 13}, id="month-thirteen"),
        ],
    )
    def test_invalid_period_is_refused(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
        params: dict[str, int],
    ) -> None:
        """US36-CA02"""
        ana = create_user(role=Role.OPERATOR)

        response = db_client.get(
            "/goals/me", params=params, headers=authenticate_as(ana)
        )

        assert response.status_code == 422


class TestGoalProgress:
    def test_achieved_amount_counts_only_own_agreements_paid_in_the_month(
        self,
        db_client: TestClient,
        db_session: Session,
        create_user: CreateUser,
        create_goal: CreateGoal,
        create_condominium: CreateCondominium,
        create_debtor: CreateDebtor,
        authenticate_as: AuthenticateAs,
    ) -> None:
        """US36-CA01"""
        ana = create_user(email="ana@example.com", name="Ana", role=Role.OPERATOR)
        rui = create_user(email="rui@example.com", name="Rui", role=Role.OPERATOR)
        create_goal(ana, target_amount=Decimal("220.00"))
        mirante = create_condominium(name="Residencial Mirante")
        jose = create_debtor(mirante, name="José Simão", unit="Bloco B 304")
        carla = create_debtor(mirante, name="Carla Nunes", unit="Bloco A 101")
        ana_agreement = close_agreement(db_client, authenticate_as(ana), mirante, jose)
        rui_agreement = close_agreement(db_client, authenticate_as(rui), mirante, carla)
        # Duas parcelas pagas em março (o primeiro e o último dia) e uma em abril.
        pay_installments(
            db_session,
            ana_agreement,
            [date(2026, 3, 1), date(2026, 3, 31), date(2026, 4, 1)],
        )
        pay_installments(db_session, rui_agreement, [date(2026, 3, 10)])

        response = db_client.get(
            "/goals/me",
            params={"year": 2026, "month": 3},
            headers=authenticate_as(ana),
        )

        assert response.status_code == 200
        assert response.json()["achieved_amount"] == "110.00"
        assert response.json()["attainment_percentage"] == "50.00"

    def test_nothing_achieved_is_zero(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        create_goal: CreateGoal,
        authenticate_as: AuthenticateAs,
    ) -> None:
        """US36-CA01"""
        ana = create_user(role=Role.OPERATOR)
        create_goal(ana, target_amount=Decimal("5000.00"))

        response = db_client.get(
            "/goals/me",
            params={"year": 2026, "month": 3},
            headers=authenticate_as(ana),
        )

        assert response.json()["achieved_amount"] == "0.00"
        assert response.json()["attainment_percentage"] == "0.00"

    def test_goal_can_be_exceeded(
        self,
        db_client: TestClient,
        db_session: Session,
        create_user: CreateUser,
        create_goal: CreateGoal,
        create_condominium: CreateCondominium,
        create_debtor: CreateDebtor,
        authenticate_as: AuthenticateAs,
    ) -> None:
        """US36-CA01"""
        ana = create_user(role=Role.OPERATOR)
        create_goal(ana, target_amount=Decimal("100.00"))
        mirante = create_condominium(name="Residencial Mirante")
        jose = create_debtor(mirante, name="José Simão", unit="Bloco B 304")
        agreement_id = close_agreement(db_client, authenticate_as(ana), mirante, jose)
        pay_installments(db_session, agreement_id, [date(2026, 3, 5), date(2026, 3, 6)])

        response = db_client.get(
            "/goals/me",
            params={"year": 2026, "month": 3},
            headers=authenticate_as(ana),
        )

        assert response.json()["achieved_amount"] == "110.00"
        assert response.json()["attainment_percentage"] == "110.00"
