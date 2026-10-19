import uuid
from decimal import Decimal

import pytest
from pydantic import ValidationError

from advocondo.acordos.fees import fee_from_percentage
from advocondo.acordos.schemas import AgreementCreateRequest

IDS = {"condominium_id": str(uuid.uuid4()), "debtor_id": str(uuid.uuid4())}
PLAN = {"installment_count": 10, "first_due_date": "2026-01-31", "fee_percentage": "10"}


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
