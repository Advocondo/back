import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from advocondo.acordos.fees import fee_from_percentage
from advocondo.acordos.lawyer_assignment import (
    LawyerNotEligibleError,
    ensure_can_be_responsible,
)
from advocondo.acordos.models import Agreement, AgreementStatus
from advocondo.acordos.schemas import AgreementCreateRequest
from advocondo.parcelas.models import Installment
from advocondo.users.models import Role, User, UserStatus

IDS = {"condominium_id": str(uuid.uuid4()), "debtor_id": str(uuid.uuid4())}
PLAN = {"installment_count": 10, "first_due_date": "2026-01-31", "fee_percentage": "10"}

NOW = datetime(2026, 3, 2, 9, 0, tzinfo=UTC)


def make_user(name: str, **fields: Any) -> User:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "email": f"{name.lower()}@example.com",
        "name": name,
        "role": Role.OPERATOR,
        "status": UserStatus.ACTIVE,
        "is_lawyer": True,
        "oab_number": "123456/DF",
    }
    return User(**{**defaults, **fields})


class TestAgreementCreateRequest:
    def test_total_amount_keeps_the_cents_exactly(self) -> None:
        request = AgreementCreateRequest.model_validate(
            {**IDS, **PLAN, "total_amount": "4500.10"}
        )

        assert request.total_amount == Decimal("4500.10")

    @pytest.mark.parametrize(
        "fields",
        [
            pytest.param({"total_amount": "0"}, id="zero-amount"),
            pytest.param({"total_amount": "-1"}, id="negative-amount"),
            pytest.param({"total_amount": "10.001"}, id="fraction-of-a-cent"),
            pytest.param({}, id="missing-amount-US15-CA02"),
            pytest.param({"total_amount": "1", "lawyer": "x"}, id="unknown-field"),
            pytest.param(
                {"total_amount": "1", "installment_count": 0}, id="no-installments"
            ),
            pytest.param(
                {"total_amount": "1", "installment_count": 121},
                id="more-than-120-installments",
            ),
        ],
    )
    def test_invalid_request_is_refused(self, fields: dict[str, object]) -> None:
        with pytest.raises(ValidationError):
            AgreementCreateRequest.model_validate({**IDS, **PLAN, **fields})

    @pytest.mark.parametrize("missing", ["condominium_id", "debtor_id"])
    def test_condominium_and_debtor_are_required(self, missing: str) -> None:
        """US15-CA02"""
        fields = {**IDS, **PLAN, "total_amount": "100"}
        del fields[missing]

        with pytest.raises(ValidationError):
            AgreementCreateRequest.model_validate(fields)


class TestFee:
    @pytest.mark.parametrize(
        ("total", "percentage", "expected"),
        [
            pytest.param("4500.00", "10", "450.00", id="ten-percent"),
            pytest.param("1200.00", "22.5", "270.00", id="fractional-percentage"),
            pytest.param("100.01", "10", "10.00", id="half-cent-down"),
            pytest.param("100.05", "10", "10.01", id="half-cent-up"),
            pytest.param("100.00", "0", "0.00", id="no-fee"),
        ],
    )
    def test_fee_from_percentage_is_rounded_to_the_cent(
        self, total: str, percentage: str, expected: str
    ) -> None:
        """US16-CA01"""
        assert fee_from_percentage(Decimal(total), Decimal(percentage)) == Decimal(
            expected
        )

    @pytest.mark.parametrize(
        "fee",
        [
            pytest.param({}, id="no-fee"),
            pytest.param({"fee_percentage": "10", "fee_amount": "10"}, id="both"),
            pytest.param({"fee_percentage": "100.01"}, id="above-100-percent"),
            pytest.param({"fee_amount": "-1"}, id="negative-amount"),
        ],
    )
    def test_fee_must_be_given_in_one_valid_way(self, fee: dict[str, str]) -> None:
        plan = {key: value for key, value in PLAN.items() if key != "fee_percentage"}

        with pytest.raises(ValidationError):
            AgreementCreateRequest.model_validate(
                {**IDS, **plan, "total_amount": "100", **fee}
            )


class TestAssignLawyer:
    def test_first_assignment_has_no_previous_lawyer(self) -> None:
        """US18-CA01"""
        agreement = Agreement()
        marina, beto = make_user("Marina"), make_user("Beto")

        changed = agreement.assign_lawyer(marina, assigned_by=beto, now=NOW)

        assert changed is True
        assert agreement.responsible_lawyer is marina
        assert [
            (a.previous_lawyer, a.new_lawyer) for a in agreement.lawyer_assignments
        ] == [(None, marina)]

    def test_reassigning_keeps_who_was_before_and_who_is_now(self) -> None:
        """US18-CA02"""
        agreement = Agreement()
        marina, rui, beto = make_user("Marina"), make_user("Rui"), make_user("Beto")

        agreement.assign_lawyer(marina, assigned_by=beto, now=NOW)
        agreement.assign_lawyer(rui, assigned_by=beto, now=NOW)

        assert agreement.responsible_lawyer is rui
        assert [
            (a.previous_lawyer, a.new_lawyer) for a in agreement.lawyer_assignments
        ] == [
            (None, marina),
            (marina, rui),
        ]

    def test_assigning_the_same_lawyer_changes_nothing(self) -> None:
        """US18-CA02"""
        agreement = Agreement()
        marina, beto = make_user("Marina"), make_user("Beto")
        agreement.assign_lawyer(marina, assigned_by=beto, now=NOW)

        changed = agreement.assign_lawyer(marina, assigned_by=beto, now=NOW)

        assert changed is False
        assert len(agreement.lawyer_assignments) == 1


class TestEnsureCanBeResponsible:
    def test_active_lawyer_can_be_responsible(self) -> None:
        """US18-CA01"""
        ensure_can_be_responsible(make_user("Marina"))

    @pytest.mark.parametrize(
        ("is_lawyer", "status"),
        [
            pytest.param(False, UserStatus.ACTIVE, id="not-a-lawyer"),
            pytest.param(True, UserStatus.PENDING, id="pending-lawyer"),
            pytest.param(True, UserStatus.INACTIVE, id="inactive-lawyer"),
        ],
    )
    def test_others_cannot_be_responsible(
        self, is_lawyer: bool, status: UserStatus
    ) -> None:
        """US18-CA01"""
        candidate = make_user("Candidato", is_lawyer=is_lawyer, status=status)

        with pytest.raises(LawyerNotEligibleError):
            ensure_can_be_responsible(candidate)


def make_installment(number: int, paid: bool = False) -> Installment:
    return Installment(
        number=number,
        due_date=date(2026, number, 10),
        amount=Decimal("100.00"),
        condominium_amount=Decimal("90.00"),
        fee_amount=Decimal("10.00"),
        payment_date=date(2026, number, 9) if paid else None,
    )


class TestCancelAgreement:
    def test_cancelling_keeps_the_moment_and_the_reason(self) -> None:
        agreement = Agreement(status=AgreementStatus.ACTIVE)

        agreement.cancel("Devedor desistiu do acordo", NOW)

        assert agreement.status == AgreementStatus.CANCELLED
        assert agreement.cancelled_at == NOW
        assert agreement.cancellation_reason == "Devedor desistiu do acordo"

    def test_the_reason_is_optional(self) -> None:
        agreement = Agreement(status=AgreementStatus.ACTIVE)

        agreement.cancel(None, NOW)

        assert agreement.status == AgreementStatus.CANCELLED
        assert agreement.cancellation_reason is None

    def test_unpaid_installments_leave_out_the_paid_ones(self) -> None:
        agreement = Agreement(
            installments=[
                make_installment(1, paid=True),
                make_installment(2),
                make_installment(3),
            ]
        )

        assert [item.number for item in agreement.unpaid_installments] == [2, 3]
