from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from advocondo.condominios.models import Condominium
from advocondo.devedores.spreadsheet import XLSX_MEDIA_TYPE
from advocondo.users.models import Role
from tests.fixtures.auth import AuthenticateAs
from tests.fixtures.condominios import CreateCondominium
from tests.fixtures.devedores import CreateDebtor
from tests.fixtures.users import CreateUser
from tests.support.spreadsheet import build_xlsx

UNKNOWN_ID = "00000000-0000-0000-0000-000000000000"


@pytest.fixture
def operator_headers(
    create_user: CreateUser, authenticate_as: AuthenticateAs
) -> dict[str, str]:
    return authenticate_as(create_user(role=Role.OPERATOR))


@pytest.fixture
def mirante(create_condominium: CreateCondominium) -> Condominium:
    return create_condominium(name="Residencial Mirante")


def new_debtor(condominium: Condominium, **fields: Any) -> dict[str, Any]:
    return {
        "condominium_id": str(condominium.id),
        "name": "José Simão",
        "unit": "Bloco B 304",
        "phone": "(61) 91234-5678",
        **fields,
    }


def register(
    client: TestClient, headers: dict[str, str], payload: dict[str, Any]
) -> httpx.Response:
    response: httpx.Response = client.post("/debtors", json=payload, headers=headers)
    return response


class TestRegisterDebtor:
    def test_operator_registers_a_debtor(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        mirante: Condominium,
    ) -> None:
        """US13"""
        response = register(db_client, operator_headers, new_debtor(mirante))

        assert response.status_code == 201
        body = response.json()
        assert body["condominium_id"] == str(mirante.id)
        assert body["name"] == "José Simão"
        assert body["phone"] == "61912345678"

    def test_similar_debtor_is_reported_instead_of_registered(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        mirante: Condominium,
        create_debtor: CreateDebtor,
    ) -> None:
        """US13-CA01"""
        registered = create_debtor(mirante, name="Jose Simao", unit="Torre A 101")

        response = register(db_client, operator_headers, new_debtor(mirante))

        assert response.status_code == 409
        body = response.json()
        assert body["detail"].startswith("Já existe devedor com dados parecidos")
        assert [debtor["id"] for debtor in body["similar_debtors"]] == [
            str(registered.id)
        ]

    def test_similar_debtor_is_registered_when_the_user_confirms(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        mirante: Condominium,
        create_debtor: CreateDebtor,
    ) -> None:
        """US13-CA01"""
        create_debtor(mirante, name="José Simão")

        response = register(
            db_client, operator_headers, new_debtor(mirante, confirm_duplicate=True)
        )

        assert response.status_code == 201

    def test_same_debtor_in_another_condominium_is_not_similar(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        mirante: Condominium,
        create_condominium: CreateCondominium,
        create_debtor: CreateDebtor,
    ) -> None:
        create_debtor(create_condominium(name="Cond. Lake View"))

        response = register(db_client, operator_headers, new_debtor(mirante))

        assert response.status_code == 201

    def test_debtor_without_phone_and_email_is_refused(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        mirante: Condominium,
    ) -> None:
        response = register(
            db_client, operator_headers, new_debtor(mirante, phone=None)
        )

        assert response.status_code == 422
        assert response.json()["detail"] == "Informe o telefone ou o e-mail do devedor."

    def test_unknown_condominium_is_not_found(
        self, db_client: TestClient, operator_headers: dict[str, str]
    ) -> None:
        payload = {
            "condominium_id": UNKNOWN_ID,
            "name": "José",
            "unit": "101",
            "phone": "61912345678",
        }

        response = register(db_client, operator_headers, payload)

        assert response.status_code == 404

    def test_client_user_is_refused(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
        mirante: Condominium,
    ) -> None:
        headers = authenticate_as(create_user(role=Role.CLIENT))

        assert register(db_client, headers, new_debtor(mirante)).status_code == 403


class TestSearchDebtors:
    def test_search_by_name_or_unit_within_a_condominium(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        mirante: Condominium,
        create_condominium: CreateCondominium,
        create_debtor: CreateDebtor,
    ) -> None:
        create_debtor(mirante, name="José Simão", unit="Bloco B 304")
        create_debtor(mirante, name="Maria Souza", unit="Torre A 101")
        create_debtor(create_condominium(name="Outro"), name="José Lima", unit="1")

        def names_found(params: dict[str, str]) -> list[str]:
            response = db_client.get(
                "/debtors", params=params, headers=operator_headers
            )
            return [debtor["name"] for debtor in response.json()]

        assert names_found({"search": "jos"}) == ["José Lima", "José Simão"]
        assert names_found({"condominium_id": str(mirante.id), "search": "jos"}) == [
            "José Simão"
        ]
        assert names_found({"search": "torre a"}) == ["Maria Souza"]

    def test_get_unknown_debtor_is_not_found(
        self, db_client: TestClient, operator_headers: dict[str, str]
    ) -> None:
        response = db_client.get(f"/debtors/{UNKNOWN_ID}", headers=operator_headers)

        assert response.status_code == 404
        assert response.json()["detail"] == "Devedor não encontrado."


class TestUpdateDebtor:
    def test_contact_data_can_be_updated(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        mirante: Condominium,
        create_debtor: CreateDebtor,
    ) -> None:
        debtor = create_debtor(mirante)

        response = db_client.patch(
            f"/debtors/{debtor.id}",
            json={"email": "jose@example.com", "phone": None},
            headers=operator_headers,
        )

        assert response.status_code == 200
        assert response.json()["email"] == "jose@example.com"
        assert response.json()["phone"] is None

    def test_removing_the_only_contact_is_refused(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        mirante: Condominium,
        create_debtor: CreateDebtor,
    ) -> None:
        debtor = create_debtor(mirante, email=None)

        response = db_client.patch(
            f"/debtors/{debtor.id}", json={"phone": None}, headers=operator_headers
        )

        assert response.status_code == 422


def import_spreadsheet(
    client: TestClient,
    headers: dict[str, str],
    condominium_id: object,
    content: bytes,
    *,
    confirm: bool = False,
) -> httpx.Response:
    response: httpx.Response = client.post(
        "/debtors/import",
        data={"condominium_id": str(condominium_id), "confirm": str(confirm).lower()},
        files={"file": ("inadimplentes.xlsx", content, XLSX_MEDIA_TYPE)},
        headers=headers,
    )
    return response


def debtor_names(
    client: TestClient, headers: dict[str, str], condominium: Condominium
) -> list[str]:
    response = client.get(
        "/debtors", params={"condominium_id": str(condominium.id)}, headers=headers
    )
    return [debtor["name"] for debtor in response.json()]


SPREADSHEET = build_xlsx(
    ("José Simão", "Bloco B 304", "(61) 91234-5678", None),
    ("Maria Souza", "Torre A 101", None, None),
    ("Carla Nunes", "Torre A 102", None, "carla@example.com"),
    ("Carla  Nunes", "Torre C 9", "61987654321", None),
)


class TestImportDebtors:
    def test_preview_points_rows_with_errors_and_saves_nothing(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        mirante: Condominium,
    ) -> None:
        """US14-CA01"""
        response = import_spreadsheet(
            db_client, operator_headers, mirante.id, SPREADSHEET
        )

        assert response.status_code == 200
        body = response.json()
        assert body["confirmed"] is False
        assert body["imported"] == 0
        assert [(row["number"], row["status"]) for row in body["rows"]] == [
            (2, "valid"),
            (3, "invalid"),
            (4, "valid"),
            (5, "similar"),
        ]
        assert body["rows"][1]["errors"] == [
            "Informe o telefone ou o e-mail do devedor."
        ]
        assert body["rows"][1]["values"]["name"] == "Maria Souza"
        assert body["rows"][3]["repeats_row"] == 4
        assert debtor_names(db_client, operator_headers, mirante) == []

    def test_confirmed_import_registers_only_the_valid_rows(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        mirante: Condominium,
        create_debtor: CreateDebtor,
    ) -> None:
        """US14-CA02"""
        registered = create_debtor(mirante, name="Jose Simao", unit="Bloco B 304")

        response = import_spreadsheet(
            db_client, operator_headers, mirante.id, SPREADSHEET, confirm=True
        )

        assert response.status_code == 200
        body = response.json()
        assert body["confirmed"] is True
        assert body["imported"] == 1
        assert body["rows"][0]["status"] == "similar"
        assert [debtor["id"] for debtor in body["rows"][0]["similar_debtors"]] == [
            str(registered.id)
        ]
        assert debtor_names(db_client, operator_headers, mirante) == [
            "Carla Nunes",
            "Jose Simao",
        ]

    def test_imported_debtor_can_be_linked_to_an_agreement(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        mirante: Condominium,
    ) -> None:
        """US14-CA02"""
        content = build_xlsx(("José Simão", "Bloco B 304", "61912345678", None))
        import_spreadsheet(
            db_client, operator_headers, mirante.id, content, confirm=True
        )
        debtor_id = db_client.get("/debtors", headers=operator_headers).json()[0]["id"]

        response = db_client.post(
            "/agreements",
            json={
                "condominium_id": str(mirante.id),
                "debtor_id": debtor_id,
                "total_amount": "5500.00",
                "installment_count": 10,
                "first_due_date": "2026-01-31",
                "fee_percentage": "10",
            },
            headers=operator_headers,
        )

        assert response.status_code == 201

    @pytest.mark.parametrize(
        ("content", "detail"),
        [
            pytest.param(
                b"Nome;Unidade",
                "Não foi possível ler a planilha. Envie um arquivo .xlsx.",
                id="not-xlsx",
            ),
            pytest.param(
                build_xlsx(("José",), headers=("Nome",)),
                "Faltam colunas na planilha: Unidade. Use o modelo de planilha.",
                id="missing-column",
            ),
        ],
    )
    def test_unreadable_spreadsheet_is_refused(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        mirante: Condominium,
        content: bytes,
        detail: str,
    ) -> None:
        response = import_spreadsheet(db_client, operator_headers, mirante.id, content)

        assert response.status_code == 422
        assert response.json()["detail"] == detail

    def test_unknown_condominium_is_not_found(
        self, db_client: TestClient, operator_headers: dict[str, str]
    ) -> None:
        response = import_spreadsheet(
            db_client, operator_headers, UNKNOWN_ID, SPREADSHEET
        )

        assert response.status_code == 404

    def test_client_user_is_refused(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
        mirante: Condominium,
    ) -> None:
        headers = authenticate_as(create_user(role=Role.CLIENT))

        response = import_spreadsheet(db_client, headers, mirante.id, SPREADSHEET)

        assert response.status_code == 403

    def test_template_is_downloaded_as_xlsx(
        self, db_client: TestClient, operator_headers: dict[str, str]
    ) -> None:
        response = db_client.get("/debtors/import/template", headers=operator_headers)

        assert response.status_code == 200
        assert response.headers["content-type"] == XLSX_MEDIA_TYPE
        assert "modelo-inadimplentes.xlsx" in response.headers["content-disposition"]
