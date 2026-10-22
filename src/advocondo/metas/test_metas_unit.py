from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from advocondo.metas.attainment import (
    calculate_attainment_percentage,
    month_range,
)
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


class TestCalculateAttainmentPercentage:
    @pytest.mark.parametrize(
        ("achieved", "target", "expected"),
        [
            pytest.param("0.00", "5000.00", "0.00", id="nothing-achieved"),
            pytest.param("110.00", "220.00", "50.00", id="half"),
            pytest.param("5000.00", "5000.00", "100.00", id="exactly-the-goal"),
            pytest.param("6250.00", "5000.00", "125.00", id="goal-exceeded"),
            pytest.param("100.00", "300.00", "33.33", id="rounds-down"),
            pytest.param("200.00", "300.00", "66.67", id="rounds-up"),
        ],
    )
    def test_percentage_of_the_goal_has_two_decimal_places(
        self, achieved: str, target: str, expected: str
    ) -> None:
        """US36-CA01"""
        result = calculate_attainment_percentage(Decimal(achieved), Decimal(target))

        assert result == Decimal(expected)


class TestMonthRange:
    @pytest.mark.parametrize(
        ("year", "month", "last_day"),
        [
            pytest.param(2026, 3, 31, id="31-day-month"),
            pytest.param(2026, 4, 30, id="30-day-month"),
            pytest.param(2026, 2, 28, id="february"),
            pytest.param(2028, 2, 29, id="february-of-a-leap-year"),
        ],
    )
    def test_range_goes_from_the_first_to_the_last_day(
        self, year: int, month: int, last_day: int
    ) -> None:
        """US36-CA01"""
        first, last = month_range(year, month)

        assert (first, last) == (date(year, month, 1), date(year, month, last_day))
