from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from advocondo.condominios.models import Condominium
from advocondo.users.models import Role
from tests.fixtures.auth import AuthenticateAs
from tests.fixtures.condominios import CreateCondominium
from tests.fixtures.devedores import CreateDebtor
from tests.fixtures.users import CreateUser

UNKNOWN_ID = "00000000-0000-0000-0000-000000000000"


@pytest.fixture
def operator_headers(
    create_user: CreateUser, authenticate_as: AuthenticateAs
) -> dict[str, str]:
    return authenticate_as(create_user(role=Role.OPERATOR))


@pytest.fixture
def mirante(create_condominium: CreateCondominium) -> Condominium:
    return create_condominium(name="Residencial Mirante")


@pytest.fixture
def register_agreement(
    db_client: TestClient,
    operator_headers: dict[str, str],
    mirante: Condominium,
    create_debtor: CreateDebtor,
) -> Any:
    """Registers an agreement through the API and returns its id."""

    def register(total_amount: str, installment_count: int, first_due_date: str) -> str:
        debtor = create_debtor(mirante)
        response = db_client.post(
            "/agreements",
            json={
                "condominium_id": str(mirante.id),
                "debtor_id": str(debtor.id),
                "total_amount": total_amount,
                "installment_count": installment_count,
                "first_due_date": first_due_date,
            },
            headers=operator_headers,
        )
        agreement_id: str = response.json()["id"]
        return agreement_id

    return register


def get_plan(
    client: TestClient, headers: dict[str, str], agreement_id: str
) -> list[dict[str, Any]]:
    response = client.get(f"/agreements/{agreement_id}/installments", headers=headers)
    plan: list[dict[str, Any]] = response.json()
    return plan


class TestInstallmentPlan:
    def test_plan_has_monthly_installments_that_add_up_to_the_total(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        register_agreement: Any,
    ) -> None:
        """US17-CA01 and US17-CA02"""
        agreement_id = register_agreement("100.00", 3, "2026-01-31")

        plan = get_plan(db_client, operator_headers, agreement_id)

        assert [installment["number"] for installment in plan] == [1, 2, 3]
        assert [installment["due_date"] for installment in plan] == [
            "2026-01-31",
            "2026-02-28",
            "2026-03-31",
        ]
        assert [installment["amount"] for installment in plan] == [
            "33.33",
            "33.33",
            "33.34",
        ]
        assert sum(Decimal(item["amount"]) for item in plan) == Decimal("100.00")
        assert all(installment["payment_date"] is None for installment in plan)

    def test_plan_of_unknown_agreement_is_not_found(
        self, db_client: TestClient, operator_headers: dict[str, str]
    ) -> None:
        response = db_client.get(
            f"/agreements/{UNKNOWN_ID}/installments", headers=operator_headers
        )

        assert response.status_code == 404
