from decimal import Decimal

import pytest
from pydantic import ValidationError

from advocondo.metas.errors import GoalOnlyForOperatorsError
from advocondo.metas.schemas import GoalRequest
from advocondo.metas.service import ensure_role_can_have_goal
from advocondo.users.models import Role


class TestEnsureRoleCanHaveGoal:
    def test_operator_can_have_a_goal(self) -> None:
        """US36-CA01"""
        ensure_role_can_have_goal(Role.OPERATOR)

    @pytest.mark.parametrize(
        "role",
        [pytest.param(Role.ADMIN, id="admin"), pytest.param(Role.CLIENT, id="client")],
    )
    def test_other_roles_cannot_have_a_goal(self, role: Role) -> None:
        """US36-CA01"""
        with pytest.raises(GoalOnlyForOperatorsError):
            ensure_role_can_have_goal(role)


class TestGoalRequest:
    @pytest.mark.parametrize(
        "target_amount",
        [
            pytest.param("5000", id="integer"),
            pytest.param("5000.5", id="one-decimal-place"),
            pytest.param("0.01", id="smallest-amount"),
            pytest.param("9999999999.99", id="largest-amount"),
        ],
    )
    def test_valid_amount_is_accepted(self, target_amount: str) -> None:
        """US36-CA01"""
        request = GoalRequest.model_validate({"target_amount": target_amount})

        assert request.target_amount == Decimal(target_amount)

    @pytest.mark.parametrize(
        "fields",
        [
            pytest.param({}, id="missing-amount"),
            pytest.param({"target_amount": "0"}, id="zero"),
            pytest.param({"target_amount": "-10.00"}, id="negative"),
            pytest.param({"target_amount": "10.005"}, id="three-decimal-places"),
            pytest.param({"target_amount": "10000000000.00"}, id="too-large"),
            pytest.param({"target_amount": "abc"}, id="not-a-number"),
            pytest.param({"target_amount": "5", "user_id": "x"}, id="unknown-field"),
        ],
    )
    def test_invalid_request_is_refused(self, fields: dict[str, object]) -> None:
        """US36-CA01"""
        with pytest.raises(ValidationError):
            GoalRequest.model_validate(fields)