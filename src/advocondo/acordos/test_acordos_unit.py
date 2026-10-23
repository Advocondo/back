import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from advocondo.acordos.errors import (
    FeeAboveTotalError,
    FeeIncompatibleWithPaidError,
    NoOpenInstallmentError,
    TotalBelowPaidAmountError,
)
from advocondo.acordos.fees import fee_from_percentage
from advocondo.acordos.lawyer_assignment import (
    LawyerNotEligibleError,
    ensure_can_be_responsible,
)
from advocondo.acordos.models import Agreement
from advocondo.acordos.renegotiation import (
    Fee,
    fee_after_edit,
    recalculate_open_installments,
)
from advocondo.acordos.schemas import AgreementCreateRequest, AgreementUpdateRequest
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


class TestAgreementUpdateRequest:
    def test_only_the_fields_sent_are_changed(self) -> None:
        """US19"""
        request = AgreementUpdateRequest(total_amount=Decimal("4000.00"))

        assert request.model_dump(exclude_unset=True) == {
            "total_amount": Decimal("4000.00")
        }
        assert request.confirm_paid_installments is False

    @pytest.mark.parametrize(
        "fields",
        [
            pytest.param({}, id="nothing-to-change"),
            pytest.param(
                {"confirm_paid_installments": True}, id="only-the-confirmation"
            ),
            pytest.param(
                {"fee_percentage": "10", "fee_amount": "500.00"},
                id="both-fee-formats",
            ),
            pytest.param({"total_amount": "0"}, id="zero-total"),
            pytest.param({"total_amount": "100", "rate": 1}, id="unknown-field"),
        ],
    )
    def test_invalid_update_is_refused(self, fields: dict[str, object]) -> None:
        """US19"""
        with pytest.raises(ValidationError):
            AgreementUpdateRequest.model_validate(fields)


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


class TestFeeAfterEdit:
    @pytest.mark.parametrize(
        ("typed_percentage", "typed_amount", "stored_percentage", "expected"),
        [
            pytest.param(
                None,
                Decimal("300.00"),
                Decimal(10),
                Fee(Decimal("300.00"), None),
                id="amount-typed-now",
            ),
            pytest.param(
                Decimal(5),
                None,
                Decimal(10),
                Fee(Decimal("200.00"), Decimal(5)),
                id="percentage-typed-now",
            ),
            pytest.param(
                None,
                None,
                Decimal(10),
                Fee(Decimal("400.00"), Decimal(10)),
                id="stored-percentage-follows-the-total",
            ),
            pytest.param(
                None,
                None,
                None,
                Fee(Decimal("550.00"), None),
                id="stored-amount-is-kept",
            ),
        ],
    )
    def test_fee_follows_what_was_typed_or_stored(
        self,
        typed_percentage: Decimal | None,
        typed_amount: Decimal | None,
        stored_percentage: Decimal | None,
        expected: Fee,
    ) -> None:
        """US19"""
        fee = fee_after_edit(
            Decimal("4000.00"),
            typed_percentage,
            typed_amount,
            stored_percentage,
            Decimal("550.00"),
        )

        assert fee == expected

    def test_fee_above_the_total_is_refused(self) -> None:
        """US19"""
        with pytest.raises(FeeAboveTotalError):
            fee_after_edit(
                Decimal("4000.00"),
                None,
                Decimal("4000.01"),
                None,
                Decimal("550.00"),
            )


class TestRecalculateOpenInstallments:
    def test_open_installments_split_what_is_left_in_equal_parts(self) -> None:
        """US19"""
        values = recalculate_open_installments(
            Decimal("5500.00"), Decimal("550.00"), Decimal(0), Decimal(0), 10
        )

        assert [value.amount for value in values] == [Decimal("550.00")] * 10
        assert [value.fee_amount for value in values] == [Decimal("55.00")] * 10

    def test_paid_installments_are_left_out_of_the_split(self) -> None:
        """US19-CA01"""
        values = recalculate_open_installments(
            Decimal("4000.00"),
            Decimal("400.00"),
            Decimal("550.00"),
            Decimal("55.00"),
            9,
        )

        assert sum(value.amount for value in values) == Decimal("3450.00")
        assert sum(value.fee_amount for value in values) == Decimal("345.00")
        assert all(0 <= value.fee_amount <= value.amount for value in values)

    @pytest.mark.parametrize(
        ("new_total", "new_fee", "paid_amount", "paid_fee", "open_count", "error"),
        [
            pytest.param(
                "4000.00",
                "400.00",
                "5500.00",
                "550.00",
                0,
                NoOpenInstallmentError,
                id="nothing-left-to-recalculate",
            ),
            pytest.param(
                "500.00",
                "50.00",
                "550.00",
                "55.00",
                9,
                TotalBelowPaidAmountError,
                id="total-below-what-was-paid",
            ),
            pytest.param(
                "550.00",
                "55.00",
                "550.00",
                "55.00",
                9,
                TotalBelowPaidAmountError,
                id="total-equal-to-what-was-paid",
            ),
            pytest.param(
                "4000.00",
                "40.00",
                "550.00",
                "55.00",
                9,
                FeeIncompatibleWithPaidError,
                id="fee-below-the-fee-received",
            ),
            pytest.param(
                "1000.00",
                "1000.00",
                "900.00",
                "0.00",
                9,
                FeeIncompatibleWithPaidError,
                id="fee-above-what-is-left",
            ),
        ],
    )
    def test_impossible_recalculation_is_refused(
        self,
        new_total: str,
        new_fee: str,
        paid_amount: str,
        paid_fee: str,
        open_count: int,
        error: type[Exception],
    ) -> None:
        """US19-CA01"""
        with pytest.raises(error):
            recalculate_open_installments(
                Decimal(new_total),
                Decimal(new_fee),
                Decimal(paid_amount),
                Decimal(paid_fee),
                open_count,
            )
