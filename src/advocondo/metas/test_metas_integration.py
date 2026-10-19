import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from advocondo.users.models import Role
from tests.fixtures.auth import AuthenticateAs
from tests.fixtures.metas import CreateGoal
from tests.fixtures.users import CreateUser


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
