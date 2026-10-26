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
        paid.receive(paid.amount, date(2026, 1, 10))
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
        assert response.json()["detail"].startswith(
            "Não há parcela seguinte sem pagamento"
        )

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
        paid.receive(paid.amount, today - timedelta(days=30))
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


class RegisterAgreementIn(Protocol):
    def __call__(
        self,
        condominium: Condominium,
        debtor_name: str,
        installment_count: int,
        first_due_date: str,
    ) -> str: ...


def list_due_in_month(
    client: TestClient, headers: dict[str, str], **params: str
) -> list[dict[str, Any]]:
    response = client.get("/installments", params=params, headers=headers)
    assert response.status_code == 200
    installments: list[dict[str, Any]] = response.json()
    return installments


def mark_as_paid(db_session: Session, installment_id: str, payment_date: date) -> None:
    """Quita a parcela direto no banco, sem depender da rota de baixa (US26)."""
    installment = db_session.get(Installment, installment_id)
    assert installment is not None
    installment.receive(installment.amount, payment_date)
    db_session.flush()


class TestMonthInstallments:
    """US25. O relógio dos testes está em 2 de março de 2026."""

    @pytest.fixture
    def register_agreement_in(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        create_debtor: CreateDebtor,
    ) -> RegisterAgreementIn:
        """Cadastra um acordo de R$ 100,00 por parcela e devolve o id dele."""

        def register(
            condominium: Condominium,
            debtor_name: str,
            installment_count: int,
            first_due_date: str,
        ) -> str:
            debtor = create_debtor(condominium, name=debtor_name)
            response = db_client.post(
                "/agreements",
                json={
                    "condominium_id": str(condominium.id),
                    "debtor_id": str(debtor.id),
                    "total_amount": str(100 * installment_count),
                    "installment_count": installment_count,
                    "first_due_date": first_due_date,
                    "fee_percentage": "10",
                },
                headers=operator_headers,
            )
            agreement_id: str = response.json()["id"]
            return agreement_id

        return register

    def test_lists_the_installments_due_in_the_current_month(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        mirante: Condominium,
        register_agreement_in: RegisterAgreementIn,
    ) -> None:
        """US25-CA01: devedor, condomínio, valor e status, pela ordem de vencimento."""
        register_agreement_in(mirante, "Ana Souza", 1, "2026-03-31")
        register_agreement_in(mirante, "José Simão", 3, "2026-02-10")

        installments = list_due_in_month(db_client, operator_headers)

        assert [item["due_date"] for item in installments] == [
            "2026-03-10",
            "2026-03-31",
        ]
        first = installments[0]
        assert first["number"] == 2
        assert first["amount"] == "100.00"
        assert first["status"] == "open"
        assert first["debtor"]["name"] == "José Simão"
        assert first["debtor"]["unit"] == "Bloco B 304"
        assert first["condominium"]["name"] == "Residencial Mirante"

    def test_another_month_can_be_listed(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        mirante: Condominium,
        register_agreement_in: RegisterAgreementIn,
    ) -> None:
        register_agreement_in(mirante, "José Simão", 3, "2026-02-10")

        installments = list_due_in_month(
            db_client, operator_headers, year="2026", month="4"
        )

        assert [item["due_date"] for item in installments] == ["2026-04-10"]

    def test_filters_by_condominium(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        mirante: Condominium,
        create_condominium: CreateCondominium,
        register_agreement_in: RegisterAgreementIn,
    ) -> None:
        """US25-CA02"""
        aurora = create_condominium(name="Edifício Aurora")
        register_agreement_in(mirante, "José Simão", 1, "2026-03-10")
        register_agreement_in(aurora, "Ana Souza", 1, "2026-03-20")

        installments = list_due_in_month(
            db_client, operator_headers, condominium_id=str(aurora.id)
        )

        assert [item["debtor"]["name"] for item in installments] == ["Ana Souza"]

    def test_filters_by_responsible_lawyer(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        mirante: Condominium,
        create_user: CreateUser,
        register_agreement_in: RegisterAgreementIn,
    ) -> None:
        """US25-CA02: o responsável é o advogado atribuído ao acordo (US18)."""
        lawyer = create_user(
            email="marina@example.com",
            name="Marina Dias",
            role=Role.OPERATOR,
            is_lawyer=True,
            oab_number="123456/DF",
        )
        assigned_agreement_id = register_agreement_in(
            mirante, "José Simão", 1, "2026-03-10"
        )
        register_agreement_in(mirante, "Ana Souza", 1, "2026-03-20")
        db_client.put(
            f"/agreements/{assigned_agreement_id}/responsible-lawyer",
            json={"lawyer_id": str(lawyer.id)},
            headers=operator_headers,
        )

        installments = list_due_in_month(
            db_client, operator_headers, responsible_lawyer_id=str(lawyer.id)
        )

        assert [item["debtor"]["name"] for item in installments] == ["José Simão"]

    @pytest.mark.parametrize(
        ("status", "debtor_name"),
        [
            pytest.param("overdue", "Carla Dias", id="overdue-since-yesterday"),
            pytest.param("open", "Bruno Lima", id="open-due-today"),
            pytest.param("paid", "Ana Souza", id="paid"),
        ],
    )
    def test_filters_by_status(
        self,
        db_client: TestClient,
        db_session: Session,
        operator_headers: dict[str, str],
        mirante: Condominium,
        register_agreement_in: RegisterAgreementIn,
        status: str,
        debtor_name: str,
    ) -> None:
        """US25-CA02: o filtro concorda com o status exibido (US27)."""
        register_agreement_in(mirante, "Carla Dias", 1, "2026-03-01")
        register_agreement_in(mirante, "Bruno Lima", 1, "2026-03-02")
        paid_agreement_id = register_agreement_in(mirante, "Ana Souza", 1, "2026-03-20")
        paid = get_plan(db_client, operator_headers, paid_agreement_id)[0]
        mark_as_paid(db_session, paid["id"], date(2026, 3, 1))

        installments = list_due_in_month(db_client, operator_headers, status=status)

        assert [item["debtor"]["name"] for item in installments] == [debtor_name]
        assert installments[0]["status"] == status

    def test_pages_through_the_month(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        mirante: Condominium,
        register_agreement_in: RegisterAgreementIn,
    ) -> None:
        for day in ("05", "10", "15"):
            register_agreement_in(mirante, f"Devedor {day}", 1, f"2026-03-{day}")

        installments = list_due_in_month(
            db_client, operator_headers, limit="2", offset="1"
        )

        assert [item["due_date"] for item in installments] == [
            "2026-03-10",
            "2026-03-15",
        ]

    @pytest.mark.parametrize(
        "params",
        [
            pytest.param({"month": "13"}, id="month-above-12"),
            pytest.param({"month": "0"}, id="month-below-1"),
            pytest.param({"status": "late"}, id="unknown-status"),
        ],
    )
    def test_invalid_filter_is_refused(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        params: dict[str, str],
    ) -> None:
        response = db_client.get(
            "/installments", params=params, headers=operator_headers
        )

        assert response.status_code == 422

    def test_client_user_is_refused(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
    ) -> None:
        headers = authenticate_as(create_user(role=Role.CLIENT))

        response = db_client.get("/installments", headers=headers)

        assert response.status_code == 403


def payment_url(installment_id: str) -> str:
    return f"/installments/{installment_id}/payment"


def pay(
    client: TestClient,
    headers: dict[str, str],
    installment_id: str,
    payment_date: str,
    amount: str | None = None,
) -> dict[str, Any]:
    """Registra um pagamento pela API e devolve a parcela atualizada."""
    payload = {"payment_date": payment_date}
    if amount is not None:
        payload["amount"] = amount
    response = client.post(payment_url(installment_id), json=payload, headers=headers)
    assert response.status_code == 200
    installment: dict[str, Any] = response.json()
    return installment


@pytest.fixture
def admin_headers(
    create_user: CreateUser, authenticate_as: AuthenticateAs
) -> dict[str, str]:
    return authenticate_as(create_user(email="admin@advocondo.test", role=Role.ADMIN))


class TestInstallmentPayment:
    """US26. O relógio dos testes está em 2 de março de 2026."""

    @pytest.fixture
    def first_installment_id(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        register_agreement: RegisterAgreement,
    ) -> str:
        """Primeira de três parcelas, vencida em 10 de fevereiro de 2026."""
        agreement_id = register_agreement("300.00", 3, "2026-02-10")
        installment_id: str = get_plan(db_client, operator_headers, agreement_id)[0][
            "id"
        ]
        return installment_id

    def test_payment_marks_the_installment_as_paid(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        first_installment_id: str,
    ) -> None:
        """US26-CA01"""
        response = db_client.post(
            payment_url(first_installment_id),
            json={"payment_date": "2026-02-12"},
            headers=operator_headers,
        )

        assert response.status_code == 200
        assert response.json()["payment_date"] == "2026-02-12"
        assert response.json()["status"] == "paid"

    def test_payment_can_be_made_before_the_due_date(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        first_installment_id: str,
    ) -> None:
        response = db_client.post(
            payment_url(first_installment_id),
            json={"payment_date": "2026-02-01"},
            headers=operator_headers,
        )

        assert response.json()["status"] == "paid"

    def test_payment_date_cannot_be_in_the_future(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        first_installment_id: str,
    ) -> None:
        response = db_client.post(
            payment_url(first_installment_id),
            json={"payment_date": "2026-03-03"},
            headers=operator_headers,
        )

        assert response.status_code == 422
        assert response.json()["detail"] == "A data do pagamento não pode ser futura."

    def test_paid_installment_cannot_be_paid_again(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        first_installment_id: str,
    ) -> None:
        url = payment_url(first_installment_id)
        db_client.post(
            url, json={"payment_date": "2026-02-12"}, headers=operator_headers
        )

        response = db_client.post(
            url, json={"payment_date": "2026-02-15"}, headers=operator_headers
        )

        assert response.status_code == 422
        assert response.json()["detail"] == (
            "Parcela já paga. Para mudar a data do pagamento, corrija a baixa."
        )

    def test_administrator_corrects_the_payment_date(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        admin_headers: dict[str, str],
        first_installment_id: str,
    ) -> None:
        """US26-CA02"""
        url = payment_url(first_installment_id)
        db_client.post(
            url, json={"payment_date": "2026-02-12"}, headers=operator_headers
        )

        response = db_client.put(
            url, json={"payment_date": "2026-02-11"}, headers=admin_headers
        )

        assert response.status_code == 200
        assert response.json()["payment_date"] == "2026-02-11"
        assert response.json()["status"] == "paid"

    def test_administrator_reverses_the_payment(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        admin_headers: dict[str, str],
        first_installment_id: str,
    ) -> None:
        """US26-CA02: a parcela vencida em fevereiro volta a constar como atrasada."""
        url = payment_url(first_installment_id)
        db_client.post(
            url, json={"payment_date": "2026-02-12"}, headers=operator_headers
        )

        response = db_client.delete(url, headers=admin_headers)

        assert response.status_code == 200
        assert response.json()["payment_date"] is None
        assert response.json()["status"] == "overdue"

    @pytest.mark.parametrize(
        "method",
        [pytest.param("PUT", id="correction"), pytest.param("DELETE", id="reversal")],
    )
    def test_operator_cannot_correct_or_reverse_a_payment(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        first_installment_id: str,
        method: str,
    ) -> None:
        """US26-CA02: só quem tem permissão, o Administrador."""
        url = payment_url(first_installment_id)
        db_client.post(
            url, json={"payment_date": "2026-02-12"}, headers=operator_headers
        )

        response = db_client.request(
            method, url, json={"payment_date": "2026-02-11"}, headers=operator_headers
        )

        assert response.status_code == 403

    @pytest.mark.parametrize(
        "method",
        [pytest.param("PUT", id="correction"), pytest.param("DELETE", id="reversal")],
    )
    def test_unpaid_installment_has_no_payment_to_change(
        self,
        db_client: TestClient,
        admin_headers: dict[str, str],
        first_installment_id: str,
        method: str,
    ) -> None:
        response = db_client.request(
            method,
            payment_url(first_installment_id),
            json={"payment_date": "2026-02-11"},
            headers=admin_headers,
        )

        assert response.status_code == 422
        assert response.json()["detail"] == "A parcela ainda não foi paga."

    @pytest.mark.parametrize("method", ["POST", "PUT", "DELETE"])
    def test_unknown_installment_is_not_found(
        self, db_client: TestClient, admin_headers: dict[str, str], method: str
    ) -> None:
        response = db_client.request(
            method,
            payment_url(UNKNOWN_ID),
            json={"payment_date": "2026-02-11"},
            headers=admin_headers,
        )

        assert response.status_code == 404

    @pytest.mark.parametrize(
        "payload",
        [
            pytest.param({}, id="without-date"),
            pytest.param({"payment_date": "12/02/2026"}, id="date-not-iso"),
            pytest.param(
                {"payment_date": "2026-02-12", "method": "pix"}, id="unknown-field"
            ),
        ],
    )
    def test_invalid_payment_is_refused(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        first_installment_id: str,
        payload: dict[str, str],
    ) -> None:
        response = db_client.post(
            payment_url(first_installment_id), json=payload, headers=operator_headers
        )

        assert response.status_code == 422

    def test_client_user_is_refused(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
        first_installment_id: str,
    ) -> None:
        headers = authenticate_as(
            create_user(email="client_payments@advocondo.test", role=Role.CLIENT)
        )

        response = db_client.post(
            payment_url(first_installment_id),
            json={"payment_date": "2026-02-12"},
            headers=headers,
        )

        assert response.status_code == 403


class TestCancelledAgreement:
    """US20. O relógio dos testes está em 2 de março de 2026."""

    @pytest.fixture
    def admin_headers(
        self, create_user: CreateUser, authenticate_as: AuthenticateAs
    ) -> dict[str, str]:
        return authenticate_as(
            create_user(email="admin_cancel@advocondo.test", role=Role.ADMIN)
        )

    @pytest.fixture
    def cancelled_agreement_id(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        register_agreement: RegisterAgreement,
    ) -> str:
        """Três parcelas de R$ 100,00 (10/02, 10/03 e 10/04), a primeira paga, e o
        acordo cancelado depois disso."""
        agreement_id = register_agreement("300.00", 3, "2026-02-10")
        first = get_plan(db_client, operator_headers, agreement_id)[0]
        db_client.post(
            payment_url(first["id"]),
            json={"payment_date": "2026-02-12"},
            headers=operator_headers,
        )
        response = db_client.post(
            f"/agreements/{agreement_id}/cancel",
            json={"confirm_open_installments": True},
            headers=operator_headers,
        )
        assert response.status_code == 200
        return agreement_id

    def test_unpaid_installments_leave_the_month_list_but_paid_ones_stay(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        cancelled_agreement_id: str,
    ) -> None:
        """US20-CA01 e CA02"""
        march = list_due_in_month(db_client, operator_headers, year="2026", month="3")
        february = list_due_in_month(
            db_client, operator_headers, year="2026", month="2"
        )

        assert march == []
        assert [(item["number"], item["status"]) for item in february] == [(1, "paid")]

    def test_active_agreements_keep_their_installments_in_the_list(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        register_agreement: RegisterAgreement,
        cancelled_agreement_id: str,
    ) -> None:
        active_id = register_agreement("100.00", 1, "2026-03-20")

        march = list_due_in_month(db_client, operator_headers, year="2026", month="3")

        assert [item["agreement_id"] for item in march] == [active_id]

    def test_plan_still_shows_every_installment(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        cancelled_agreement_id: str,
    ) -> None:
        """US20-CA02: o histórico fica consultável, as pagas e as sem pagamento."""
        plan = get_plan(db_client, operator_headers, cancelled_agreement_id)

        assert [item["number"] for item in plan] == [1, 2, 3]
        assert plan[0]["status"] == "paid"
        assert plan[0]["payment_date"] == "2026-02-12"

    def test_unpaid_installment_cannot_be_paid(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        cancelled_agreement_id: str,
    ) -> None:
        second = get_plan(db_client, operator_headers, cancelled_agreement_id)[1]

        response = db_client.post(
            payment_url(second["id"]),
            json={"payment_date": "2026-03-01"},
            headers=operator_headers,
        )

        assert response.status_code == 422
        assert response.json() == {
            "detail": "Acordo cancelado não aceita esta operação."
        }
        plan = get_plan(db_client, operator_headers, cancelled_agreement_id)
        assert plan[1]["payment_date"] is None

    def test_unpaid_installment_cannot_be_edited(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        cancelled_agreement_id: str,
    ) -> None:
        second = get_plan(db_client, operator_headers, cancelled_agreement_id)[1]

        response = db_client.patch(
            f"/installments/{second['id']}",
            json={"due_date": "2026-03-15"},
            headers=operator_headers,
        )

        assert response.status_code == 422
        assert response.json() == {
            "detail": "Acordo cancelado não aceita esta operação."
        }

    def test_administrator_can_still_fix_a_payment_made_by_mistake(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        admin_headers: dict[str, str],
        cancelled_agreement_id: str,
    ) -> None:
        """Sem reativação, é o único jeito de consertar uma baixa errada."""
        first = get_plan(db_client, operator_headers, cancelled_agreement_id)[0]

        corrected = db_client.put(
            payment_url(first["id"]),
            json={"payment_date": "2026-02-11"},
            headers=admin_headers,
        )
        reversed_payment = db_client.delete(
            payment_url(first["id"]), headers=admin_headers
        )

        assert corrected.status_code == 200
        assert corrected.json()["payment_date"] == "2026-02-11"
        assert reversed_payment.status_code == 200
        assert reversed_payment.json()["payment_date"] is None
        # Estornada, a parcela é uma sem pagamento de acordo cancelado: sai da lista
        # do mês e não aceita nova baixa.
        february = list_due_in_month(
            db_client, operator_headers, year="2026", month="2"
        )
        repaid = db_client.post(
            payment_url(first["id"]),
            json={"payment_date": "2026-02-12"},
            headers=operator_headers,
        )
        assert february == []
        assert repaid.status_code == 422


class TestPartialPayment:
    """US28. O relógio dos testes está em 2 de março de 2026."""

    @pytest.fixture
    def plan_ids(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        register_agreement: RegisterAgreement,
    ) -> list[str]:
        """Quatro parcelas de R$ 100,00, com vencimento no dia 10, de março a junho."""
        agreement_id = register_agreement("400.00", 4, "2026-03-10")
        return [
            item["id"] for item in get_plan(db_client, operator_headers, agreement_id)
        ]

    def test_partial_payment_keeps_the_remaining_amount_open(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        plan_ids: list[str],
    ) -> None:
        """US28-CA01"""
        installment = pay(
            db_client, operator_headers, plan_ids[0], "2026-03-01", amount="40.00"
        )

        assert installment["remaining_amount"] == "60.00"
        assert installment["payment_date"] is None
        assert installment["status"] == "open"

    def test_payments_that_reach_the_amount_pay_the_installment(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        plan_ids: list[str],
    ) -> None:
        """US28-CA01: quitada no dia do pagamento que zera o saldo."""
        pay(db_client, operator_headers, plan_ids[0], "2026-02-20", amount="40.00")

        installment = pay(
            db_client, operator_headers, plan_ids[0], "2026-03-01", amount="60.00"
        )

        assert installment["remaining_amount"] == "0.00"
        assert installment["payment_date"] == "2026-03-01"
        assert installment["status"] == "paid"

    def test_history_shows_each_payment(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        plan_ids: list[str],
    ) -> None:
        """US28-CA02"""
        pay(db_client, operator_headers, plan_ids[0], "2026-02-20", amount="40.00")
        pay(db_client, operator_headers, plan_ids[0], "2026-03-01", amount="25.50")

        response = db_client.get(
            f"/installments/{plan_ids[0]}/payments", headers=operator_headers
        )

        assert response.status_code == 200
        assert [(item["amount"], item["payment_date"]) for item in response.json()] == [
            ("40.00", "2026-02-20"),
            ("25.50", "2026-03-01"),
        ]

    def test_payment_without_amount_settles_the_remaining_amount(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        plan_ids: list[str],
    ) -> None:
        """US26-CA01 continua valendo: sem valor, a baixa quita o saldo."""
        pay(db_client, operator_headers, plan_ids[0], "2026-02-20", amount="40.00")

        installment = pay(db_client, operator_headers, plan_ids[0], "2026-03-01")

        history = db_client.get(
            f"/installments/{plan_ids[0]}/payments", headers=operator_headers
        ).json()
        assert installment["status"] == "paid"
        assert [item["amount"] for item in history] == ["40.00", "60.00"]

    def test_payment_above_the_remaining_amount_is_refused(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        plan_ids: list[str],
    ) -> None:
        pay(db_client, operator_headers, plan_ids[0], "2026-02-20", amount="40.00")

        response = db_client.post(
            payment_url(plan_ids[0]),
            json={"payment_date": "2026-03-01", "amount": "60.01"},
            headers=operator_headers,
        )

        assert response.status_code == 422
        assert response.json()["detail"] == (
            "O valor pago é maior que o saldo em aberto da parcela."
        )

    def test_reversal_also_removes_partial_payments(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        admin_headers: dict[str, str],
        plan_ids: list[str],
    ) -> None:
        """US26-CA02: estornar vale para a parcela paga em parte."""
        pay(db_client, operator_headers, plan_ids[0], "2026-02-20", amount="40.00")

        response = db_client.delete(payment_url(plan_ids[0]), headers=admin_headers)

        history = db_client.get(
            f"/installments/{plan_ids[0]}/payments", headers=operator_headers
        ).json()
        assert response.status_code == 200
        assert response.json()["remaining_amount"] == "100.00"
        assert history == []

    def test_correction_changes_the_date_of_the_payment_that_settled(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        admin_headers: dict[str, str],
        plan_ids: list[str],
    ) -> None:
        """US26-CA02: a data da baixa é a do pagamento que quitou a parcela."""
        pay(db_client, operator_headers, plan_ids[0], "2026-02-20", amount="40.00")
        pay(db_client, operator_headers, plan_ids[0], "2026-03-01", amount="60.00")

        response = db_client.put(
            payment_url(plan_ids[0]),
            json={"payment_date": "2026-02-28"},
            headers=admin_headers,
        )

        history = db_client.get(
            f"/installments/{plan_ids[0]}/payments", headers=operator_headers
        ).json()
        assert response.json()["payment_date"] == "2026-02-28"
        assert [item["payment_date"] for item in history] == [
            "2026-02-20",
            "2026-02-28",
        ]

    def test_partially_paid_installment_cannot_be_edited(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        plan_ids: list[str],
    ) -> None:
        """O novo valor poderia ficar abaixo do que já foi pago (US17-CA03)."""
        pay(db_client, operator_headers, plan_ids[0], "2026-03-01", amount="40.00")

        response = db_client.patch(
            f"/installments/{plan_ids[0]}",
            json={"amount": "30.00"},
            headers=operator_headers,
        )

        assert response.status_code == 422
        assert response.json()["detail"] == (
            "Parcela com pagamento parcial não pode ser editada."
        )

    def test_partially_paid_installment_does_not_absorb_a_difference(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        plan_ids: list[str],
    ) -> None:
        """A 3ª, paga em parte, fica com o mesmo valor; só a 4ª absorve (US17-CA03)."""
        pay(db_client, operator_headers, plan_ids[2], "2026-03-01", amount="40.00")

        response = db_client.patch(
            f"/installments/{plan_ids[1]}",
            json={"amount": "130.00"},
            headers=operator_headers,
        )

        assert response.status_code == 200
        assert amounts(response.json()) == ["100.00", "130.00", "100.00", "70.00"]

    @pytest.mark.parametrize(
        "amount",
        [
            pytest.param("0", id="zero"),
            pytest.param("-10.00", id="negative"),
            pytest.param("10.001", id="fraction-of-a-cent"),
        ],
    )
    def test_invalid_amount_is_refused(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        plan_ids: list[str],
        amount: str,
    ) -> None:
        response = db_client.post(
            payment_url(plan_ids[0]),
            json={"payment_date": "2026-03-01", "amount": amount},
            headers=operator_headers,
        )

        assert response.status_code == 422

    def test_history_of_unknown_installment_is_not_found(
        self, db_client: TestClient, operator_headers: dict[str, str]
    ) -> None:
        response = db_client.get(
            f"/installments/{UNKNOWN_ID}/payments", headers=operator_headers
        )

        assert response.status_code == 404

    def test_client_user_cannot_see_the_history(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
        plan_ids: list[str],
    ) -> None:
        headers = authenticate_as(
            create_user(email="client_partial@advocondo.test", role=Role.CLIENT)
        )

        response = db_client.get(
            f"/installments/{plan_ids[0]}/payments", headers=headers
        )

        assert response.status_code == 403


def invoice_url(installment_id: str) -> str:
    return f"/installments/{installment_id}/invoice"


class TestInvoice:
    """US29. O relógio dos testes está em 2 de março de 2026."""

    @pytest.fixture
    def plan_ids(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        register_agreement: RegisterAgreement,
    ) -> list[str]:
        """Três parcelas de R$ 100,00, com vencimento no dia 10, de janeiro a março."""
        agreement_id = register_agreement("300.00", 3, "2026-01-10")
        return [
            item["id"] for item in get_plan(db_client, operator_headers, agreement_id)
        ]

    def test_invoice_is_linked_to_the_paid_installment(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        plan_ids: list[str],
    ) -> None:
        """US29-CA01"""
        pay(db_client, operator_headers, plan_ids[0], "2026-01-10")

        response = db_client.put(
            invoice_url(plan_ids[0]),
            json={"number": "202600000000042", "issue_date": "2026-01-12"},
            headers=operator_headers,
        )

        assert response.status_code == 200
        assert response.json()["invoice_number"] == "202600000000042"
        assert response.json()["invoice_date"] == "2026-01-12"

    def test_registering_again_replaces_the_invoice(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        plan_ids: list[str],
    ) -> None:
        pay(db_client, operator_headers, plan_ids[0], "2026-01-10")
        url = invoice_url(plan_ids[0])
        db_client.put(
            url,
            json={"number": "41", "issue_date": "2026-01-12"},
            headers=operator_headers,
        )

        response = db_client.put(
            url,
            json={"number": "42", "issue_date": "2026-01-13"},
            headers=operator_headers,
        )

        assert response.json()["invoice_number"] == "42"
        assert response.json()["invoice_date"] == "2026-01-13"

    @pytest.mark.parametrize(
        "amount_paid",
        [pytest.param(None, id="unpaid"), pytest.param("40.00", id="partially-paid")],
    )
    def test_installment_must_be_paid(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        plan_ids: list[str],
        amount_paid: str | None,
    ) -> None:
        """US29-CA01: a nota é da parcela paga."""
        if amount_paid is not None:
            pay(db_client, operator_headers, plan_ids[0], "2026-01-10", amount_paid)

        response = db_client.put(
            invoice_url(plan_ids[0]),
            json={"number": "42", "issue_date": "2026-01-12"},
            headers=operator_headers,
        )

        assert response.status_code == 422
        assert response.json()["detail"] == "A parcela ainda não foi paga."

    def test_issue_date_cannot_be_in_the_future(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        plan_ids: list[str],
    ) -> None:
        pay(db_client, operator_headers, plan_ids[0], "2026-01-10")

        response = db_client.put(
            invoice_url(plan_ids[0]),
            json={"number": "42", "issue_date": "2026-03-03"},
            headers=operator_headers,
        )

        assert response.status_code == 422
        assert response.json()["detail"] == (
            "A data de emissão da nota fiscal não pode ser futura."
        )

    def test_lists_the_paid_installments_without_invoice(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        plan_ids: list[str],
    ) -> None:
        """US29-CA02: a 1ª tem nota, a 2ª está paga sem nota e a 3ª não foi paga."""
        pay(db_client, operator_headers, plan_ids[0], "2026-01-10")
        pay(db_client, operator_headers, plan_ids[1], "2026-02-10")
        db_client.put(
            invoice_url(plan_ids[0]),
            json={"number": "42", "issue_date": "2026-01-12"},
            headers=operator_headers,
        )

        response = db_client.get(
            "/installments/paid-without-invoice", headers=operator_headers
        )

        assert response.status_code == 200
        assert [item["id"] for item in response.json()] == [plan_ids[1]]
        assert response.json()[0]["debtor"]["name"] == "José Simão"

    def test_paid_installments_without_invoice_come_by_payment_date(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        plan_ids: list[str],
    ) -> None:
        pay(db_client, operator_headers, plan_ids[0], "2026-02-15")
        pay(db_client, operator_headers, plan_ids[1], "2026-02-01")

        response = db_client.get(
            "/installments/paid-without-invoice",
            params={"limit": "1"},
            headers=operator_headers,
        )

        assert [item["id"] for item in response.json()] == [plan_ids[1]]

    def test_reversal_keeps_the_invoice(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        admin_headers: dict[str, str],
        plan_ids: list[str],
    ) -> None:
        """A nota emitida continua emitida: estornar o pagamento não a apaga."""
        pay(db_client, operator_headers, plan_ids[0], "2026-01-10")
        db_client.put(
            invoice_url(plan_ids[0]),
            json={"number": "42", "issue_date": "2026-01-12"},
            headers=operator_headers,
        )

        response = db_client.delete(payment_url(plan_ids[0]), headers=admin_headers)

        assert response.json()["invoice_number"] == "42"

    @pytest.mark.parametrize(
        "payload",
        [
            pytest.param({"number": "12a", "issue_date": "2026-01-12"}, id="letters"),
            pytest.param(
                {"number": "1234567890123456", "issue_date": "2026-01-12"},
                id="more-than-15-digits",
            ),
            pytest.param({"number": "", "issue_date": "2026-01-12"}, id="empty"),
            pytest.param({"number": "42"}, id="without-date"),
            pytest.param(
                {"number": "42", "issue_date": "2026-01-12", "series": "1"},
                id="unknown-field",
            ),
        ],
    )
    def test_invalid_invoice_is_refused(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        plan_ids: list[str],
        payload: dict[str, str],
    ) -> None:
        pay(db_client, operator_headers, plan_ids[0], "2026-01-10")

        response = db_client.put(
            invoice_url(plan_ids[0]), json=payload, headers=operator_headers
        )

        assert response.status_code == 422

    def test_unknown_installment_is_not_found(
        self, db_client: TestClient, operator_headers: dict[str, str]
    ) -> None:
        response = db_client.put(
            invoice_url(UNKNOWN_ID),
            json={"number": "42", "issue_date": "2026-01-12"},
            headers=operator_headers,
        )

        assert response.status_code == 404

    def test_client_user_is_refused(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
    ) -> None:
        headers = authenticate_as(
            create_user(email="client_invoice@advocondo.test", role=Role.CLIENT)
        )

        response = db_client.get("/installments/paid-without-invoice", headers=headers)

        assert response.status_code == 403


def financial_history_url(agreement_id: str) -> str:
    return f"/agreements/{agreement_id}/financial-history"


def changes(history: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """As linhas do histórico pelo tipo de movimentação. Com o relógio parado, as
    movimentações de um teste têm o mesmo horário e a ordem entre elas não importa."""
    return {entry["change"]: entry for entry in history}


class TestFinancialHistory:
    """US31. O relógio dos testes está em 2 de março de 2026, às 9h (UTC)."""

    @pytest.fixture
    def agreement_id(self, register_agreement: RegisterAgreement) -> str:
        """Três parcelas de R$ 100,00, com vencimento no dia 10, de fevereiro a abril."""
        return register_agreement("300.00", 3, "2026-02-10")

    @pytest.fixture
    def first_installment_id(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        agreement_id: str,
    ) -> str:
        installment_id: str = get_plan(db_client, operator_headers, agreement_id)[0][
            "id"
        ]
        return installment_id

    def get_history(
        self, client: TestClient, headers: dict[str, str], agreement_id: str
    ) -> list[dict[str, Any]]:
        response = client.get(financial_history_url(agreement_id), headers=headers)
        assert response.status_code == 200
        history: list[dict[str, Any]] = response.json()
        return history

    def test_payment_is_logged_with_who_when_and_amount(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
        admin_headers: dict[str, str],
        agreement_id: str,
        first_installment_id: str,
    ) -> None:
        """US31-CA01"""
        sarah = create_user(email="sarah@advocondo.test", name="Sarah Lima")
        pay(
            db_client,
            authenticate_as(sarah),
            first_installment_id,
            "2026-02-12",
            amount="40.00",
        )

        history = self.get_history(db_client, admin_headers, agreement_id)

        assert history == [
            {
                "changed_at": "2026-03-02T09:00:00Z",
                "changed_by": {"id": str(sarah.id), "name": "Sarah Lima"},
                "change": "payment_recorded",
                "installment_number": 1,
                "field": None,
                "old_value": None,
                "new_value": "40.00",
            }
        ]

    def test_correction_logs_the_old_and_the_new_payment_date(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        admin_headers: dict[str, str],
        agreement_id: str,
        first_installment_id: str,
    ) -> None:
        """US31-CA01"""
        pay(db_client, operator_headers, first_installment_id, "2026-02-12")

        db_client.put(
            payment_url(first_installment_id),
            json={"payment_date": "2026-02-11"},
            headers=admin_headers,
        )

        history = self.get_history(db_client, admin_headers, agreement_id)

        correction = changes(history)["payment_corrected"]
        assert (correction["old_value"], correction["new_value"]) == (
            "2026-02-12",
            "2026-02-11",
        )

    def test_correction_to_the_same_date_is_not_logged(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        admin_headers: dict[str, str],
        agreement_id: str,
        first_installment_id: str,
    ) -> None:
        pay(db_client, operator_headers, first_installment_id, "2026-02-12")

        db_client.put(
            payment_url(first_installment_id),
            json={"payment_date": "2026-02-12"},
            headers=admin_headers,
        )

        history = self.get_history(db_client, admin_headers, agreement_id)
        assert [entry["change"] for entry in history] == ["payment_recorded"]

    def test_reversal_logs_the_reversed_amount(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        admin_headers: dict[str, str],
        agreement_id: str,
        first_installment_id: str,
    ) -> None:
        """US31-CA01: o estorno desfaz também os pagamentos parciais (US28)."""
        pay(db_client, operator_headers, first_installment_id, "2026-02-12", "40.00")
        pay(db_client, operator_headers, first_installment_id, "2026-02-20", "20.00")

        db_client.delete(payment_url(first_installment_id), headers=admin_headers)

        history = self.get_history(db_client, admin_headers, agreement_id)

        reversal = changes(history)["payment_reversed"]
        assert (reversal["old_value"], reversal["new_value"]) == ("60.00", None)

    def test_installment_edit_logs_amount_and_due_date(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        admin_headers: dict[str, str],
        agreement_id: str,
        first_installment_id: str,
    ) -> None:
        """US31-CA01"""
        db_client.patch(
            f"/installments/{first_installment_id}",
            json={"amount": "130.00", "due_date": "2026-02-15"},
            headers=operator_headers,
        )

        history = self.get_history(db_client, admin_headers, agreement_id)

        amount = changes(history)["amount_edited"]
        due_date = changes(history)["due_date_edited"]
        assert (amount["old_value"], amount["new_value"]) == ("100.00", "130.00")
        assert (due_date["old_value"], due_date["new_value"]) == (
            "2026-02-10",
            "2026-02-15",
        )

    def test_edit_with_the_same_due_date_is_not_logged(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        admin_headers: dict[str, str],
        agreement_id: str,
        first_installment_id: str,
    ) -> None:
        db_client.patch(
            f"/installments/{first_installment_id}",
            json={"due_date": "2026-02-10"},
            headers=operator_headers,
        )

        assert self.get_history(db_client, admin_headers, agreement_id) == []

    def test_agreement_edit_is_part_of_the_history(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        admin_headers: dict[str, str],
        agreement_id: str,
    ) -> None:
        """US31-CA01, com as alterações do acordo registradas pela US19."""
        db_client.patch(
            f"/agreements/{agreement_id}",
            json={"total_amount": "600.00"},
            headers=operator_headers,
        )

        history = self.get_history(db_client, admin_headers, agreement_id)

        total = next(entry for entry in history if entry["field"] == "total_amount")
        assert total["change"] == "agreement_edited"
        assert total["installment_number"] is None
        assert (total["old_value"], total["new_value"]) == ("300.00", "600.00")

    def test_history_starts_with_the_most_recent_change(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        admin_headers: dict[str, str],
        agreement_id: str,
        first_installment_id: str,
        clock: FrozenClock,
    ) -> None:
        pay(db_client, operator_headers, first_installment_id, "2026-02-12")
        clock.advance(timedelta(minutes=5))
        db_client.delete(payment_url(first_installment_id), headers=admin_headers)

        history = self.get_history(db_client, admin_headers, agreement_id)

        assert [entry["change"] for entry in history] == [
            "payment_reversed",
            "payment_recorded",
        ]
        assert [entry["changed_at"] for entry in history] == [
            "2026-03-02T09:05:00Z",
            "2026-03-02T09:00:00Z",
        ]

    def test_operator_cannot_see_the_history(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        agreement_id: str,
    ) -> None:
        """US31-CA02"""
        response = db_client.get(
            financial_history_url(agreement_id), headers=operator_headers
        )

        assert response.status_code == 403

    def test_client_user_cannot_see_the_history(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
        agreement_id: str,
    ) -> None:
        """US31-CA02"""
        headers = authenticate_as(
            create_user(email="client_history@advocondo.test", role=Role.CLIENT)
        )

        response = db_client.get(financial_history_url(agreement_id), headers=headers)

        assert response.status_code == 403

    def test_history_of_unknown_agreement_is_not_found(
        self, db_client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        response = db_client.get(
            financial_history_url(UNKNOWN_ID), headers=admin_headers
        )

        assert response.status_code == 404
