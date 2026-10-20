import pytest
from pydantic import ValidationError

from advocondo.condominios.cnpj import is_valid_cnpj, normalize_cnpj
from advocondo.condominios.schemas import (
    CondominiumCreateRequest,
    CondominiumUpdateRequest,
)

VALID_CNPJ = "14447918000198"
# Example from the Receita Federal for the alphanumeric CNPJ.
VALID_ALPHANUMERIC_CNPJ = "12ABC34501DE35"


class TestIsValidCnpj:
    @pytest.mark.parametrize(
        "cnpj",
        [
            pytest.param(VALID_CNPJ, id="numeric"),
            pytest.param(VALID_ALPHANUMERIC_CNPJ, id="alphanumeric"),
        ],
    )
    def test_cnpj_with_right_check_digits_is_valid(self, cnpj: str) -> None:
        assert is_valid_cnpj(cnpj)

    @pytest.mark.parametrize(
        "cnpj",
        [
            pytest.param("14447918000199", id="wrong-check-digit"),
            pytest.param("11111111111111", id="all-digits-equal"),
            pytest.param("1444791800019", id="too-short"),
            pytest.param("12ABC34501DE36", id="alphanumeric-wrong-check-digit"),
            pytest.param("12ABC34501DEA5", id="letter-in-check-digit"),
            pytest.param("12abc34501de35", id="not-normalized"),
            pytest.param("12ABC3450*DE35", id="invalid-character"),
        ],
    )
    def test_invalid_cnpj_is_refused(self, cnpj: str) -> None:
        assert not is_valid_cnpj(cnpj)

    def test_mask_is_removed_and_letters_are_uppercased(self) -> None:
        assert normalize_cnpj(" 12.abc.345/01de-35 ") == VALID_ALPHANUMERIC_CNPJ


class TestCondominiumCreateRequest:
    def test_masked_fields_are_stored_as_digits(self) -> None:
        request = CondominiumCreateRequest(
            name=" Residencial Mirante ",
            cnpj="14.447.918/0001-98",
            zip_code="12345-678",
            state="df",
            manager_phone="(61) 91234-5678",
        )

        assert request.name == "Residencial Mirante"
        assert request.cnpj == VALID_CNPJ
        assert request.zip_code == "12345678"
        assert request.state == "DF"
        assert request.manager_phone == "61912345678"

    @pytest.mark.parametrize(
        "fields",
        [
            pytest.param({}, id="missing-name"),
            pytest.param({"name": "   "}, id="blank-name"),
            pytest.param({"name": "X", "cnpj": "14447918000199"}, id="invalid-cnpj"),
            pytest.param({"name": "X", "zip_code": "123"}, id="short-zip-code"),
            pytest.param({"name": "X", "state": "DFX"}, id="state-not-two-letters"),
            pytest.param({"name": "X", "manager_phone": "123"}, id="short-phone"),
            pytest.param({"name": "X", "manager_email": "rita@"}, id="invalid-email"),
            pytest.param({"name": "X", "units": 96}, id="unknown-field"),
        ],
    )
    def test_invalid_request_is_refused(self, fields: dict[str, object]) -> None:
        with pytest.raises(ValidationError):
            CondominiumCreateRequest.model_validate(fields)


class TestCondominiumUpdateRequest:
    def test_only_the_fields_sent_are_changed(self) -> None:
        request = CondominiumUpdateRequest(manager_name="Nova Administradora")

        assert request.model_dump(exclude_unset=True) == {
            "manager_name": "Nova Administradora"
        }

    @pytest.mark.parametrize(
        "fields",
        [
            pytest.param({}, id="nothing-to-change"),
            pytest.param({"name": None}, id="name-removed"),
        ],
    )
    def test_invalid_update_is_refused(self, fields: dict[str, object]) -> None:
        with pytest.raises(ValidationError):
            CondominiumUpdateRequest.model_validate(fields)
