import uuid
from decimal import Decimal

import pytest
from pydantic import ValidationError

from advocondo.acordos.schemas import AgreementCreateRequest

IDS = {"condominium_id": str(uuid.uuid4()), "debtor_id": str(uuid.uuid4())}


class TestAgreementCreateRequest:
    def test_total_amount_keeps_the_cents_exactly(self) -> None:
        request = AgreementCreateRequest.model_validate(
            {**IDS, "total_amount": "4500.10"}
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
        ],
    )
    def test_invalid_request_is_refused(self, fields: dict[str, object]) -> None:
        with pytest.raises(ValidationError):
            AgreementCreateRequest.model_validate({**IDS, **fields})

    @pytest.mark.parametrize("missing", ["condominium_id", "debtor_id"])
    def test_condominium_and_debtor_are_required(self, missing: str) -> None:
        """US15-CA02"""
        fields = {**IDS, "total_amount": "100"}
        del fields[missing]

        with pytest.raises(ValidationError):
            AgreementCreateRequest.model_validate(fields)
