import uuid

import pytest
from pydantic import ValidationError

from advocondo.devedores.models import Debtor
from advocondo.devedores.schemas import DebtorCreateRequest, DebtorUpdateRequest
from advocondo.devedores.similarity import comparable_unit, find_similar_debtors

CONDOMINIUM_ID = uuid.uuid4()


def make_debtor(name: str, unit: str) -> Debtor:
    return Debtor(
        condominium_id=CONDOMINIUM_ID, name=name, unit=unit, phone="61912345678"
    )


class TestFindSimilarDebtors:
    @pytest.mark.parametrize(
        ("name", "unit"),
        [
            pytest.param("José Simão", "Torre A 101", id="same-name"),
            pytest.param(
                "JOSE  SIMAO", "Torre A 101", id="name-without-accents-or-case"
            ),
            pytest.param("Maria Souza", "Bloco B 304", id="same-unit"),
            pytest.param("Maria Souza", "bloco b-304", id="unit-written-differently"),
        ],
    )
    def test_debtor_with_same_name_or_unit_is_similar(
        self, name: str, unit: str
    ) -> None:
        """US13-CA01"""
        registered = make_debtor("José Simão", "Bloco B 304")

        assert find_similar_debtors(name, unit, [registered]) == [registered]

    def test_debtor_with_other_name_and_unit_is_not_similar(self) -> None:
        registered = make_debtor("José Simão", "Bloco B 304")

        assert find_similar_debtors("Maria Souza", "Bloco C 12", [registered]) == []


def test_comparable_unit_keeps_only_letters_and_numbers() -> None:
    assert comparable_unit("Bloco B - 304") == comparable_unit("blocob304")


class TestDebtorCreateRequest:
    def test_masked_phone_is_stored_as_digits(self) -> None:
        request = DebtorCreateRequest(
            condominium_id=CONDOMINIUM_ID,
            name=" José Simão ",
            unit="Bloco B 304",
            phone="(61) 91234-5678",
        )

        assert request.name == "José Simão"
        assert request.phone == "61912345678"
        assert request.confirm_duplicate is False

    @pytest.mark.parametrize(
        "fields",
        [
            pytest.param({"unit": "101"}, id="missing-name"),
            pytest.param({"name": "José"}, id="missing-unit"),
            pytest.param(
                {"name": "José", "unit": "101", "phone": "123"}, id="short-phone"
            ),
            pytest.param(
                {"name": "José", "unit": "101", "email": "jose@"}, id="invalid-email"
            ),
            pytest.param(
                {"name": "José", "unit": "101", "cpf": "1"}, id="unknown-field"
            ),
        ],
    )
    def test_invalid_request_is_refused(self, fields: dict[str, object]) -> None:
        with pytest.raises(ValidationError):
            DebtorCreateRequest.model_validate(
                {"condominium_id": str(CONDOMINIUM_ID), **fields}
            )


class TestDebtorUpdateRequest:
    @pytest.mark.parametrize(
        "fields",
        [
            pytest.param({}, id="nothing-to-change"),
            pytest.param({"name": None}, id="name-removed"),
            pytest.param({"unit": None}, id="unit-removed"),
        ],
    )
    def test_invalid_update_is_refused(self, fields: dict[str, object]) -> None:
        with pytest.raises(ValidationError):
            DebtorUpdateRequest.model_validate(fields)
