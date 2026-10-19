from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Protocol

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from advocondo.common.clock import today_in_brazil
from advocondo.condominios.models import Condominium
from advocondo.parcelas.models import Installment
from advocondo.users.models import Role
from tests.fixtures.auth import AuthenticateAs
from tests.fixtures.condominios import CreateCondominium
from tests.fixtures.devedores import CreateDebtor
from tests.fixtures.users import CreateUser
from tests.support.clock import FrozenClock

UNKNOWN_ID = "00000000-0000-0000-0000-000000000000"


class RegisterAgreement(Protocol):
    def __call__(
        self, total_amount: str, installment_count: int, first_due_date: str
    ) -> str: ...


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
) -> RegisterAgreement:
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
                "fee_percentage": "10",
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
        register_agreement: RegisterAgreement,
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


def amounts(plan: list[dict[str, Any]]) -> list[str]:
    return [installment["amount"] for installment in plan]


class TestFeeSplit:
    def test_each_installment_shows_condominium_and_fee_parts(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        register_agreement: RegisterAgreement,
    ) -> None:
        """US16-CA01 and US16-CA02: 10% fee on R$ 100,00 in 3 installments."""
        agreement_id = register_agreement("100.00", 3, "2026-01-10")

        plan = get_plan(db_client, operator_headers, agreement_id)

        assert [item["fee_amount"] for item in plan] == ["3.33", "3.34", "3.33"]
        assert sum(Decimal(item["fee_amount"]) for item in plan) == Decimal("10.00")
        for installment in plan:
            assert Decimal(installment["condominium_amount"]) + Decimal(
                installment["fee_amount"]
            ) == Decimal(installment["amount"])


class TestUpdateInstallment:
    def test_new_amount_is_absorbed_by_the_following_open_installments(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        register_agreement: RegisterAgreement,
    ) -> None:
        """US17-CA03, keeping US17-CA02"""
        agreement_id = register_agreement("400.00", 4, "2026-01-10")
        second = get_plan(db_client, operator_headers, agreement_id)[1]

        response = db_client.patch(
            f"/installments/{second['id']}",
            json={"amount": "130.00"},
            headers=operator_headers,
        )

        assert response.status_code == 200
        assert amounts(response.json()) == ["100.00", "130.00", "85.00", "85.00"]
        assert [item["fee_amount"] for item in response.json()] == [
            "10.00",
            "13.00",
            "8.50",
            "8.50",
        ]
        assert amounts(get_plan(db_client, operator_headers, agreement_id)) == [
            "100.00",
            "130.00",
            "85.00",
            "85.00",
        ]

    def test_due_date_can_be_changed(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        register_agreement: RegisterAgreement,
    ) -> None:
        """US17-CA03"""
        agreement_id = register_agreement("300.00", 3, "2026-01-10")
        first = get_plan(db_client, operator_headers, agreement_id)[0]

        response = db_client.patch(
            f"/installments/{first['id']}",
            json={"due_date": "2026-01-20"},
            headers=operator_headers,
        )

        assert response.json()[0]["due_date"] == "2026-01-20"
        assert amounts(response.json()) == ["100.00", "100.00", "100.00"]

    def test_paid_installment_cannot_be_edited(
        self,
        db_client: TestClient,
        db_session: Session,
        operator_headers: dict[str, str],
        register_agreement: RegisterAgreement,
    ) -> None:
        """US17-CA03: only before the payment (US26)."""
        agreement_id = register_agreement("300.00", 3, "2026-01-10")
        first = get_plan(db_client, operator_headers, agreement_id)[0]
        paid = db_session.get(Installment, first["id"])
        assert paid is not None
        paid.payment_date = date(2026, 1, 10)
        db_session.flush()

        response = db_client.patch(
            f"/installments/{first['id']}",
            json={"due_date": "2026-01-20"},
            headers=operator_headers,
        )

        assert response.status_code == 422
        assert response.json()["detail"] == "Parcela já paga não pode ser editada."

    def test_amount_of_the_last_installment_cannot_change(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        register_agreement: RegisterAgreement,
    ) -> None:
        agreement_id = register_agreement("300.00", 3, "2026-01-10")
        last = get_plan(db_client, operator_headers, agreement_id)[-1]

        response = db_client.patch(
            f"/installments/{last['id']}",
            json={"amount": "150.00"},
            headers=operator_headers,
        )

        assert response.status_code == 422
        assert response.json()["detail"].startswith("Não há parcela seguinte em aberto")

    def test_unknown_installment_is_not_found(
        self, db_client: TestClient, operator_headers: dict[str, str]
    ) -> None:
        response = db_client.patch(
            f"/installments/{UNKNOWN_ID}",
            json={"amount": "1.00"},
            headers=operator_headers,
        )

        assert response.status_code == 404


class TestInstallmentStatus:
    def test_status_is_calculated_from_the_dates(
        self,
        db_client: TestClient,
        db_session: Session,
        operator_headers: dict[str, str],
        register_agreement: RegisterAgreement,
        clock: FrozenClock,
    ) -> None:
        """US27-CA01"""
        today = today_in_brazil(clock.now())
        agreement_id = register_agreement(
            "300.00", 3, (today - timedelta(days=35)).isoformat()
        )
        first = get_plan(db_client, operator_headers, agreement_id)[0]
        paid = db_session.get(Installment, first["id"])
        assert paid is not None
        paid.payment_date = today - timedelta(days=30)
        db_session.flush()

        plan = get_plan(db_client, operator_headers, agreement_id)

        assert [installment["status"] for installment in plan] == [
            "paid",
            "overdue",
            "open",
        ]

    def test_installment_becomes_overdue_the_day_after_its_due_date(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
        register_agreement: RegisterAgreement,
        clock: FrozenClock,
    ) -> None:
        """US27-CA01: sem job, o status muda sozinho com o passar dos dias."""
        user = create_user(email="operator_overdue@advocondo.test", role=Role.OPERATOR)
        operator_headers = authenticate_as(user)

        today = today_in_brazil(clock.now())
        agreement_id = register_agreement("100.00", 1, today.isoformat())

        on_due_date = get_plan(db_client, operator_headers, agreement_id)[0]["status"]
        clock.advance(timedelta(days=1))
        operator_headers = authenticate_as(user)

        next_day = get_plan(db_client, operator_headers, agreement_id)[0]["status"]

        assert on_due_date == "open"
        assert next_day == "overdue"
