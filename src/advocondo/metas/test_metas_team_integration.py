from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from advocondo.users.models import Role, UserStatus
from tests.fixtures.auth import AuthenticateAs
from tests.fixtures.metas import CreateGoal
from tests.fixtures.users import CreateUser

PERIOD = {"year": 2026, "month": 3}


@pytest.fixture
def admin_headers(
    create_user: CreateUser, authenticate_as: AuthenticateAs
) -> dict[str, str]:
    return authenticate_as(create_user(email="adm@example.com", role=Role.ADMIN))


class TestTeamGoals:
    def test_lists_active_operators_with_and_without_a_goal(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        create_goal: CreateGoal,
        admin_headers: dict[str, str],
    ) -> None:
        bia = create_user(email="bia@example.com", name="Bia")
        create_user(email="ana@example.com", name="Ana")
        create_user(email="caio@example.com", name="Caio", status=UserStatus.INACTIVE)
        create_user(email="cli@example.com", name="Cliente", role=Role.CLIENT)
        create_goal(bia, target_amount=Decimal("5000.00"))

        response = db_client.get("/goals", params=PERIOD, headers=admin_headers)

        assert response.status_code == 200
        assert response.json() == [
            {
                "user_id": response.json()[0]["user_id"],
                "user_name": "Ana",
                "target_amount": None,
                "achieved_amount": "0.00",
                "attainment_percentage": None,
            },
            {
                "user_id": str(bia.id),
                "user_name": "Bia",
                "target_amount": "5000.00",
                "achieved_amount": "0.00",
                "attainment_percentage": "0.00",
            },
        ]

    def test_a_goal_of_another_month_does_not_count(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        create_goal: CreateGoal,
        admin_headers: dict[str, str],
    ) -> None:
        create_goal(create_user(email="bia@example.com"), month=4)

        response = db_client.get("/goals", params=PERIOD, headers=admin_headers)

        assert response.json()[0]["target_amount"] is None

    @pytest.mark.parametrize(
        "role",
        [
            pytest.param(Role.OPERATOR, id="operator"),
            pytest.param(Role.CLIENT, id="client"),
        ],
    )
    def test_only_the_administrator_sees_the_team(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
        role: Role,
    ) -> None:
        """US36-CA02"""
        headers = authenticate_as(create_user(role=role))

        response = db_client.get("/goals", params=PERIOD, headers=headers)

        assert response.status_code == 403

    @pytest.mark.parametrize(
        "params",
        [
            pytest.param({"year": 2026, "month": 13}, id="invalid-month"),
            pytest.param({"year": 2026}, id="no-month"),
        ],
    )
    def test_invalid_period_is_refused(
        self,
        db_client: TestClient,
        admin_headers: dict[str, str],
        params: dict[str, int],
    ) -> None:
        response = db_client.get("/goals", params=params, headers=admin_headers)

        assert response.status_code == 422
