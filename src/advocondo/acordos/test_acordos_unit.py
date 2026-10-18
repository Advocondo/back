import uuid
from decimal import Decimal

import pytest
from pydantic import ValidationError

from advocondo.acordos.schemas import AgreementCreateRequest

IDS = {"condominium_id": str(uuid.uuid4()), "debtor_id": str(uuid.uuid4())}
PLAN = {"installment_count": 10, "first_due_date": "2026-01-31"}


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
