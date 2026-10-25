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
