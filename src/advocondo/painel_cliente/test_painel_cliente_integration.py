from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from advocondo.acordos.models import Agreement
from advocondo.common.storage import DatabaseStorage
from advocondo.condominios.models import Condominium
from advocondo.config import Settings
from advocondo.devedores.models import Debtor
from advocondo.notificacoes.models import (
    ClientNotificationEvent,
    ClientNotificationLog,
)
from advocondo.notificacoes.repository import ClientNotificationRepository
from advocondo.notificacoes.service import ClientNotificationService
from advocondo.painel_cliente.models import CondominiumMonthlyReport
from advocondo.painel_cliente.monthly_report_repository import (
    CondominiumMonthlyReportRepository,
)
from advocondo.painel_cliente.monthly_report_service import (
    CondominiumMonthlyReportService,
)
from advocondo.users.models import Role, User
from tests.fixtures.auth import AuthenticateAs
from tests.fixtures.condominios import CreateCondominium
from tests.fixtures.devedores import CreateDebtor
from tests.fixtures.painel_cliente import (
    CreateAgreementWithInstallments,
    LinkClient,
)
from tests.fixtures.users import CreateUser
from tests.support.clock import FrozenClock
from tests.support.email import Outbox
from tests.support.pdf import pdf_text

URL = "/client-panel/agreements"
REPORT_URL = "/client-panel/condominiums/{condominium_id}/report"
# The default FrozenClock is 2026-03-02 09:00 UTC, which is 06:00 in Brasília.
TODAY = date(2026, 3, 2)
FORBIDDEN_FIELDS = {
    "total_amount",
    "fee_amount",
    "fee_percentage",
    "amount",
    "condominium_amount",
}


@pytest.fixture
def client_user(create_user: CreateUser) -> User:
    return create_user(role=Role.CLIENT, email="sindico@example.com")


@pytest.fixture
def client_headers(
    client_user: User, authenticate_as: AuthenticateAs
) -> dict[str, str]:
    return authenticate_as(client_user)


@pytest.fixture
def mirante(create_condominium: CreateCondominium) -> Condominium:
    return create_condominium(name="Residencial Mirante")


@pytest.fixture
def aurora(create_condominium: CreateCondominium) -> Condominium:
    return create_condominium(name="Edifício Aurora")


@pytest.fixture
def jose(mirante: Condominium, create_debtor: CreateDebtor) -> Debtor:
    return create_debtor(mirante, name="José Simão", unit="Bloco B 304")


@pytest.fixture
def maria(aurora: Condominium, create_debtor: CreateDebtor) -> Debtor:
    return create_debtor(aurora, name="Maria Souza", unit="Apto 12")


class TestClientSeesOnlyLinkedCondominiums:
    def test_client_sees_only_linked_condominiums_agreements(
        self,
        db_client: TestClient,
        client_user: User,
        client_headers: dict[str, str],
        link_client: LinkClient,
        create_condominium: CreateCondominium,
        create_debtor: CreateDebtor,
        mirante: Condominium,
        aurora: Condominium,
        jose: Debtor,
        maria: Debtor,
        create_agreement_with_installments: CreateAgreementWithInstallments,
    ) -> None:
        """US37-CA01"""
        other = create_condominium(name="Condomínio Alheio")
        stranger = create_debtor(other, name="Estranho", unit="1")
        upcoming = [(date(2026, 4, 10), None)]
        linked_mirante = create_agreement_with_installments(mirante, jose, upcoming)
        linked_aurora = create_agreement_with_installments(aurora, maria, upcoming)
        create_agreement_with_installments(other, stranger, upcoming)
        link_client(client_user, mirante, aurora)

        response = db_client.get(URL, headers=client_headers)

        assert response.status_code == 200
        assert {item["id"] for item in response.json()} == {
            str(linked_mirante.id),
            str(linked_aurora.id),
        }

    def test_client_without_condominiums_gets_empty_list(
        self,
        db_client: TestClient,
        client_headers: dict[str, str],
        mirante: Condominium,
        jose: Debtor,
        create_agreement_with_installments: CreateAgreementWithInstallments,
    ) -> None:
        """US10-CA02"""
        create_agreement_with_installments(mirante, jose, [(date(2026, 4, 10), None)])

        response = db_client.get(URL, headers=client_headers)

        assert response.status_code == 200
        assert response.json() == []

    def test_other_clients_link_does_not_show_agreements(
        self,
        db_client: TestClient,
        client_headers: dict[str, str],
        create_user: CreateUser,
        link_client: LinkClient,
        mirante: Condominium,
        jose: Debtor,
        create_agreement_with_installments: CreateAgreementWithInstallments,
    ) -> None:
        create_agreement_with_installments(mirante, jose, [(date(2026, 4, 10), None)])
        link_client(create_user(role=Role.CLIENT, email="outro@example.com"), mirante)

        response = db_client.get(URL, headers=client_headers)

        assert response.json() == []


class TestCondominiumReport:
    def test_report_contains_only_linked_condominium_client_data_and_safe_totals(
        self,
        db_client: TestClient,
        client_user: User,
        client_headers: dict[str, str],
        link_client: LinkClient,
        mirante: Condominium,
        aurora: Condominium,
        jose: Debtor,
        maria: Debtor,
        create_agreement_with_installments: CreateAgreementWithInstallments,
    ) -> None:
        create_agreement_with_installments(
            mirante,
            jose,
            [(date(2026, 2, 1), date(2026, 2, 5)), (date(2026, 4, 10), None)],
        )
        create_agreement_with_installments(aurora, maria, [(date(2026, 2, 1), None)])
        link_client(client_user, mirante)

        response = db_client.get(
            REPORT_URL.format(condominium_id=mirante.id), headers=client_headers
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        content = pdf_text(response.content)
        assert "Residencial Mirante" in content
        assert "José Simão" in content
        assert "Cliente: " + client_user.name in content
        assert "Edifício Aurora" not in content
        assert "Maria Souza" not in content
        assert "Honorários" not in content
        assert "Comissão" not in content
        assert "fee_amount" not in content
        assert "fee_percentage" not in content
        assert "condominium_amount" not in content

    def test_report_hides_unlinked_condominium_as_not_found(
        self,
        db_client: TestClient,
        client_headers: dict[str, str],
        mirante: Condominium,
    ) -> None:
        response = db_client.get(
            REPORT_URL.format(condominium_id=mirante.id), headers=client_headers
        )

        assert response.status_code == 404


class TestAgreementStatusFollowsInstallments:
    def test_response_shape_and_ordering(
        self,
        db_client: TestClient,
        client_user: User,
        client_headers: dict[str, str],
        link_client: LinkClient,
        mirante: Condominium,
        aurora: Condominium,
        jose: Debtor,
        maria: Debtor,
        create_agreement_with_installments: CreateAgreementWithInstallments,
    ) -> None:
        create_agreement_with_installments(aurora, maria, [(date(2026, 4, 10), None)])
        late = create_agreement_with_installments(
            mirante,
            jose,
            [
                (date(2026, 1, 10), None),
                (date(2026, 2, 10), None),
                (date(2026, 5, 10), None),
            ],
        )
        link_client(client_user, mirante, aurora)

        response = db_client.get(URL, headers=client_headers)

        assert response.json() == [
            {
                "id": str(late.id),
                "condominium_name": "Residencial Mirante",
                "debtor_id": str(jose.id),
                "debtor_name": "José Simão",
                "debtor_unit": "Bloco B 304",
                "status": "atrasado",
                "overdue_installments": 2,
                "next_due_date": "2026-05-10",
            },
            {
                "id": response.json()[1]["id"],
                "condominium_name": "Edifício Aurora",
                "debtor_id": str(maria.id),
                "debtor_name": "Maria Souza",
                "debtor_unit": "Apto 12",
                "status": "em_dia",
                "overdue_installments": 0,
                "next_due_date": "2026-04-10",
            },
        ]

    @pytest.mark.parametrize(
        ("installments", "expected"),
        [
            pytest.param(
                [(date(2026, 3, 1), date(2026, 3, 20))], "em_dia", id="paid-late"
            ),
            pytest.param([(TODAY, None)], "em_dia", id="due-today"),
            pytest.param([(date(2026, 3, 1), None)], "atrasado", id="due-yesterday"),
        ],
    )
    def test_agreement_status_follows_installment_status(
        self,
        db_client: TestClient,
        client_user: User,
        client_headers: dict[str, str],
        link_client: LinkClient,
        mirante: Condominium,
        jose: Debtor,
        create_agreement_with_installments: CreateAgreementWithInstallments,
        installments: Sequence[tuple[date, date | None]],
        expected: str,
    ) -> None:
        """US37-CA02"""
        create_agreement_with_installments(mirante, jose, installments)
        link_client(client_user, mirante)

        response = db_client.get(URL, headers=client_headers)

        assert [item["status"] for item in response.json()] == [expected]

    def test_today_is_the_brazilian_date_not_the_utc_one(
        self,
        db_client: TestClient,
        client_user: User,
        clock: FrozenClock,
        authenticate_as: AuthenticateAs,
        link_client: LinkClient,
        mirante: Condominium,
        jose: Debtor,
        create_agreement_with_installments: CreateAgreementWithInstallments,
    ) -> None:
        """At 01:00 UTC on 03/03 it is still 22:00 on 03/02 in Brasília, so an
        installment due on 03/02 is not overdue yet."""
        clock.advance(datetime(2026, 3, 3, 1, 0, tzinfo=UTC) - clock.now())
        headers = authenticate_as(client_user)
        create_agreement_with_installments(mirante, jose, [(date(2026, 3, 2), None)])
        link_client(client_user, mirante)

        response = db_client.get(URL, headers=headers)

        assert response.json()[0]["status"] == "em_dia"


def test_response_has_no_financial_fields(
    db_client: TestClient,
    client_user: User,
    client_headers: dict[str, str],
    link_client: LinkClient,
    mirante: Condominium,
    jose: Debtor,
    create_agreement_with_installments: CreateAgreementWithInstallments,
) -> None:
    """US37-CA02"""
    create_agreement_with_installments(mirante, jose, [(date(2026, 4, 10), None)])
    link_client(client_user, mirante)

    response = db_client.get(URL, headers=client_headers)

    item = response.json()[0]
    assert FORBIDDEN_FIELDS.isdisjoint(item)
    assert set(item) == {
        "id",
        "condominium_name",
        "debtor_id",
        "debtor_name",
        "debtor_unit",
        "status",
        "overdue_installments",
        "next_due_date",
    }


class TestAccess:
    @pytest.mark.parametrize("role", [Role.ADMIN, Role.OPERATOR])
    def test_only_client_role_can_use_panel(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
        role: Role,
    ) -> None:
        headers = authenticate_as(create_user(role=role, email="staff@example.com"))

        response = db_client.get(URL, headers=headers)

        assert response.status_code == 403

    def test_anonymous_gets_401(self, db_client: TestClient) -> None:
        assert db_client.get(URL).status_code == 401


class TestThroughTheRealRoutes:
    def test_client_sees_agreement_registered_for_a_linked_condominium(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
        client_user: User,
        client_headers: dict[str, str],
        mirante: Condominium,
        jose: Debtor,
    ) -> None:
        """Admin links the condominium (US10), the operator registers the agreement
        (US15, US17) and the Client reads the panel (US37)."""
        admin_headers = authenticate_as(
            create_user(role=Role.ADMIN, email="a@example.com")
        )
        operator_headers = authenticate_as(
            create_user(role=Role.OPERATOR, email="o@example.com")
        )
        before = db_client.get(URL, headers=client_headers)
        link = db_client.put(
            f"/users/{client_user.id}/condominiums",
            json={"condominium_ids": [str(mirante.id)]},
            headers=admin_headers,
        )
        registered = db_client.post(
            "/agreements",
            json={
                "condominium_id": str(mirante.id),
                "debtor_id": str(jose.id),
                "total_amount": "1000.00",
                "installment_count": 2,
                "first_due_date": "2026-03-31",
                "fee_percentage": "10",
            },
            headers=operator_headers,
        )

        response = db_client.get(URL, headers=client_headers)

        assert before.json() == []
        assert link.status_code == 200
        assert registered.status_code == 201
        assert response.json() == [
            {
                "id": registered.json()["id"],
                "condominium_name": "Residencial Mirante",
                "debtor_id": str(jose.id),
                "debtor_name": "José Simão",
                "debtor_unit": "Bloco B 304",
                "status": "em_dia",
                "overdue_installments": 0,
                "next_due_date": "2026-03-31",
            }
        ]

    def test_cancelled_agreement_is_hidden(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
        link_client: LinkClient,
        client_user: User,
        client_headers: dict[str, str],
        mirante: Condominium,
        jose: Debtor,
    ) -> None:
        """US20: o operador cancela o acordo e o Cliente deixa de vê-lo no painel."""
        link_client(client_user, mirante)
        operator_headers = authenticate_as(
            create_user(role=Role.OPERATOR, email="o@example.com")
        )
        registered = db_client.post(
            "/agreements",
            json={
                "condominium_id": str(mirante.id),
                "debtor_id": str(jose.id),
                "total_amount": "1000.00",
                "installment_count": 2,
                "first_due_date": "2026-03-31",
                "fee_percentage": "10",
            },
            headers=operator_headers,
        )
        before = db_client.get(URL, headers=client_headers)

        cancelled = db_client.post(
            f"/agreements/{registered.json()['id']}/cancel",
            json={"confirm_open_installments": True},
            headers=operator_headers,
        )
        after = db_client.get(URL, headers=client_headers)

        assert len(before.json()) == 1
        assert cancelled.status_code == 200
        assert after.json() == []

    def test_reactivated_agreement_shows_up_again(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
        link_client: LinkClient,
        client_user: User,
        client_headers: dict[str, str],
        mirante: Condominium,
        jose: Debtor,
    ) -> None:
        """#88: o acordo reativado volta ao painel do Cliente."""
        link_client(client_user, mirante)
        operator_headers = authenticate_as(
            create_user(role=Role.OPERATOR, email="o@example.com")
        )
        agreement_id = db_client.post(
            "/agreements",
            json={
                "condominium_id": str(mirante.id),
                "debtor_id": str(jose.id),
                "total_amount": "1000.00",
                "installment_count": 2,
                "first_due_date": "2026-03-31",
                "fee_percentage": "10",
            },
            headers=operator_headers,
        ).json()["id"]
        db_client.post(
            f"/agreements/{agreement_id}/cancel",
            json={"confirm_open_installments": True},
            headers=operator_headers,
        )

        reactivated = db_client.post(
            f"/agreements/{agreement_id}/reactivate", headers=operator_headers
        )
        after = db_client.get(URL, headers=client_headers)

        assert reactivated.status_code == 200
        assert [item["id"] for item in after.json()] == [agreement_id]


def test_agreements_are_ordered_by_condominium_then_debtor_name(
    db_client: TestClient,
    client_user: User,
    client_headers: dict[str, str],
    link_client: LinkClient,
    mirante: Condominium,
    aurora: Condominium,
    create_debtor: CreateDebtor,
    create_agreement_with_installments: CreateAgreementWithInstallments,
) -> None:
    upcoming = [(date(2026, 4, 10), None)]
    for condominium, name in [
        (mirante, "Bia"),
        (aurora, "Zé"),
        (mirante, "Ana"),
    ]:
        debtor = create_debtor(condominium, name=name)
        create_agreement_with_installments(condominium, debtor, upcoming)
    link_client(client_user, mirante, aurora)

    response = db_client.get(URL, headers=client_headers)

    assert [(i["condominium_name"], i["debtor_name"]) for i in response.json()] == [
        ("Edifício Aurora", "Zé"),
        ("Residencial Mirante", "Ana"),
        ("Residencial Mirante", "Bia"),
    ]


def installments_url(agreement_id: object) -> str:
    return f"{URL}/{agreement_id}/installments"


class TestClientInstallments:
    """#89-CA02 e CA03. Hoje é 2 de março de 2026."""

    @pytest.fixture
    def agreement(
        self,
        create_agreement_with_installments: CreateAgreementWithInstallments,
        link_client: LinkClient,
        client_user: User,
        mirante: Condominium,
        jose: Debtor,
    ) -> Agreement:
        """Três parcelas de R$ 100,00: a primeira paga, a segunda atrasada e a
        terceira em aberto."""
        link_client(client_user, mirante)
        return create_agreement_with_installments(
            mirante,
            jose,
            [
                (date(2026, 2, 10), date(2026, 2, 12)),
                (date(2026, 2, 28), None),
                (date(2026, 3, 31), None),
            ],
        )

    def test_lists_only_the_unpaid_installments(
        self,
        db_client: TestClient,
        client_headers: dict[str, str],
        agreement: Agreement,
    ) -> None:
        """#89-CA02"""
        response = db_client.get(installments_url(agreement.id), headers=client_headers)

        assert response.status_code == 200
        assert response.json() == [
            {
                "number": 2,
                "due_date": "2026-02-28",
                "amount": "100.00",
                "remaining_amount": "100.00",
                "status": "overdue",
            },
            {
                "number": 3,
                "due_date": "2026-03-31",
                "amount": "100.00",
                "remaining_amount": "100.00",
                "status": "open",
            },
        ]

    def test_fees_and_the_split_of_the_amount_are_not_shown(
        self,
        db_client: TestClient,
        client_headers: dict[str, str],
        agreement: Agreement,
    ) -> None:
        """#89-CA02 e US38-CA01"""
        response = db_client.get(installments_url(agreement.id), headers=client_headers)

        for item in response.json():
            assert set(item) == {
                "number",
                "due_date",
                "amount",
                "remaining_amount",
                "status",
            }

    def test_partly_paid_installment_shows_what_is_left(
        self,
        db_client: TestClient,
        db_session: Session,
        client_headers: dict[str, str],
        agreement: Agreement,
    ) -> None:
        """US28: o pagamento parcial não quita a parcela."""
        agreement.installments[1].receive(Decimal("40.00"), date(2026, 3, 1))
        db_session.commit()

        response = db_client.get(installments_url(agreement.id), headers=client_headers)

        second = response.json()[0]
        assert second["number"] == 2
        assert second["amount"] == "100.00"
        assert second["remaining_amount"] == "60.00"

    def test_agreement_of_another_condominium_is_not_found(
        self,
        db_client: TestClient,
        client_headers: dict[str, str],
        agreement: Agreement,
        create_agreement_with_installments: CreateAgreementWithInstallments,
        aurora: Condominium,
        maria: Debtor,
    ) -> None:
        """#89-CA03"""
        other = create_agreement_with_installments(
            aurora, maria, [(date(2026, 3, 31), None)]
        )

        response = db_client.get(installments_url(other.id), headers=client_headers)

        assert response.status_code == 404
        assert response.json() == {"detail": "Acordo não encontrado."}

    def test_cancelled_agreement_is_not_found(
        self,
        db_client: TestClient,
        db_session: Session,
        client_headers: dict[str, str],
        agreement: Agreement,
    ) -> None:
        """#89-CA03"""
        agreement.cancel(None, datetime(2026, 3, 1, tzinfo=UTC))
        db_session.commit()

        response = db_client.get(installments_url(agreement.id), headers=client_headers)

        assert response.status_code == 404

    def test_unknown_agreement_is_not_found(
        self, db_client: TestClient, client_headers: dict[str, str]
    ) -> None:
        response = db_client.get(
            installments_url("00000000-0000-0000-0000-000000000000"),
            headers=client_headers,
        )

        assert response.status_code == 404

    def test_office_staff_cannot_use_the_client_panel(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
        agreement: Agreement,
    ) -> None:
        headers = authenticate_as(
            create_user(role=Role.OPERATOR, email="o@example.com")
        )

        response = db_client.get(installments_url(agreement.id), headers=headers)

        assert response.status_code == 403

    def test_requires_a_session(
        self, db_client: TestClient, agreement: Agreement
    ) -> None:
        response = db_client.get(installments_url(agreement.id))

        assert response.status_code == 401


def history_url(debtor_id: object) -> str:
    return f"/client-panel/debtors/{debtor_id}/history"


class TestDebtorHistory:
    """US38. Hoje é 2 de março de 2026."""

    @pytest.fixture
    def linked(
        self, link_client: LinkClient, client_user: User, mirante: Condominium
    ) -> None:
        link_client(client_user, mirante)

    def test_paid_and_open_totals_by_month(
        self,
        db_client: TestClient,
        client_headers: dict[str, str],
        linked: None,
        create_agreement_with_installments: CreateAgreementWithInstallments,
        mirante: Condominium,
        jose: Debtor,
    ) -> None:
        """US38-CA01"""
        create_agreement_with_installments(
            mirante,
            jose,
            [
                (date(2026, 1, 10), date(2026, 1, 9)),
                (date(2026, 2, 10), None),
                (date(2026, 3, 10), None),
            ],
        )

        response = db_client.get(history_url(jose.id), headers=client_headers)

        assert response.status_code == 200
        assert response.json() == {
            "debtor_name": "José Simão",
            "debtor_unit": "Bloco B 304",
            "months": [
                {
                    "month": "2026-01",
                    "paid_amount": "100.00",
                    "open_amount": "0.00",
                    "status": "pago",
                },
                {
                    "month": "2026-02",
                    "paid_amount": "0.00",
                    "open_amount": "100.00",
                    "status": "atrasado",
                },
                {
                    "month": "2026-03",
                    "paid_amount": "0.00",
                    "open_amount": "100.00",
                    "status": "em_aberto",
                },
            ],
        }

    def test_no_fees_are_shown(
        self,
        db_client: TestClient,
        client_headers: dict[str, str],
        linked: None,
        create_agreement_with_installments: CreateAgreementWithInstallments,
        mirante: Condominium,
        jose: Debtor,
    ) -> None:
        """US38-CA01: sem honorários do escritório (US16)."""
        create_agreement_with_installments(mirante, jose, [(date(2026, 3, 10), None)])

        body = db_client.get(history_url(jose.id), headers=client_headers).json()

        assert set(body) == {"debtor_name", "debtor_unit", "months"}
        assert set(body["months"][0]) == {
            "month",
            "paid_amount",
            "open_amount",
            "status",
        }

    def test_cancelled_agreement_keeps_only_what_was_paid(
        self,
        db_client: TestClient,
        db_session: Session,
        client_headers: dict[str, str],
        linked: None,
        create_agreement_with_installments: CreateAgreementWithInstallments,
        mirante: Condominium,
        jose: Debtor,
    ) -> None:
        """US38 e US20: o pago fica no histórico; o não pago saiu da cobrança."""
        agreement = create_agreement_with_installments(
            mirante,
            jose,
            [(date(2026, 1, 10), date(2026, 1, 9)), (date(2026, 2, 10), None)],
        )
        agreement.cancel(None, datetime(2026, 2, 15, tzinfo=UTC))
        db_session.commit()

        response = db_client.get(history_url(jose.id), headers=client_headers)

        assert response.json()["months"] == [
            {
                "month": "2026-01",
                "paid_amount": "100.00",
                "open_amount": "0.00",
                "status": "pago",
            }
        ]

    def test_debtor_without_agreements_has_an_empty_history(
        self,
        db_client: TestClient,
        client_headers: dict[str, str],
        linked: None,
        jose: Debtor,
    ) -> None:
        response = db_client.get(history_url(jose.id), headers=client_headers)

        assert response.status_code == 200
        assert response.json()["months"] == []

    def test_debtor_of_another_condominium_is_not_found(
        self,
        db_client: TestClient,
        client_headers: dict[str, str],
        linked: None,
        create_agreement_with_installments: CreateAgreementWithInstallments,
        aurora: Condominium,
        maria: Debtor,
    ) -> None:
        create_agreement_with_installments(aurora, maria, [(date(2026, 3, 10), None)])

        response = db_client.get(history_url(maria.id), headers=client_headers)

        assert response.status_code == 404
        assert response.json() == {"detail": "Devedor não encontrado."}

    def test_unknown_debtor_is_not_found(
        self, db_client: TestClient, client_headers: dict[str, str], linked: None
    ) -> None:
        response = db_client.get(
            history_url("00000000-0000-0000-0000-000000000000"),
            headers=client_headers,
        )

        assert response.status_code == 404

    def test_panel_gives_the_debtor_id_to_open_the_history(
        self,
        db_client: TestClient,
        client_headers: dict[str, str],
        linked: None,
        create_agreement_with_installments: CreateAgreementWithInstallments,
        mirante: Condominium,
        jose: Debtor,
    ) -> None:
        create_agreement_with_installments(mirante, jose, [(date(2026, 3, 10), None)])

        panel = db_client.get(URL, headers=client_headers).json()

        assert panel[0]["debtor_id"] == str(jose.id)

    def test_office_staff_cannot_use_the_client_panel(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
        jose: Debtor,
    ) -> None:
        headers = authenticate_as(
            create_user(role=Role.OPERATOR, email="o@example.com")
        )

        response = db_client.get(history_url(jose.id), headers=headers)

        assert response.status_code == 403

    def test_requires_a_session(self, db_client: TestClient, jose: Debtor) -> None:
        response = db_client.get(history_url(jose.id))

        assert response.status_code == 401


def test_monthly_report_is_snapshotted_notified_and_downloadable(
    db_client: TestClient,
    db_session: Session,
    outbox: Outbox,
    clock: FrozenClock,
    settings: Settings,
    client_user: User,
    client_headers: dict[str, str],
    link_client: LinkClient,
    mirante: Condominium,
    jose: Debtor,
    create_agreement_with_installments: CreateAgreementWithInstallments,
) -> None:
    create_agreement_with_installments(
        mirante,
        jose,
        [(date(2026, 2, 10), date(2026, 2, 12))],
    )
    link_client(client_user, mirante)
    notification_service = ClientNotificationService(
        db_session,
        ClientNotificationRepository(db_session),
        outbox,
        clock,
        settings.frontend_url,
    )
    report_service = CondominiumMonthlyReportService(
        db_session,
        CondominiumMonthlyReportRepository(db_session),
        notification_service,
        DatabaseStorage(),
        clock,
    )

    result = report_service.close_previous_month()
    report = db_session.scalars(select(CondominiumMonthlyReport)).one()
    response = db_client.get(
        f"/client-panel/condominiums/{mirante.id}/reports/2026/2",
        headers=client_headers,
    )

    assert result.year == 2026
    assert result.month == 2
    assert result.reports_created == 1
    assert report.condominium_id == mirante.id
    assert report.generated_at == clock.now()
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["cache-control"] == "no-store"
    assert "Período: 02/2026" in pdf_text(response.content)
    assert outbox.messages[-1].to == client_user.email
    assert "relatório mensal referente a 02/2026" in outbox.messages[-1].body
    assert "Acesse o painel" not in outbox.messages[-1].body
    logs = db_session.scalars(select(ClientNotificationLog)).all()
    assert len(logs) == 1
    assert logs[0].event_type == ClientNotificationEvent.MONTHLY_REPORT_READY
    assert logs[0].sent_at == clock.now()
    assert logs[0].link is None

    repeated = report_service.close_previous_month()

    assert repeated.reports_created == 0
    assert len(outbox.messages) == 1
    assert len(db_session.scalars(select(ClientNotificationLog)).all()) == 1


def test_monthly_report_is_not_downloadable_by_unlinked_client(
    db_client: TestClient,
    db_session: Session,
    outbox: Outbox,
    clock: FrozenClock,
    settings: Settings,
    client_user: User,
    link_client: LinkClient,
    create_agreement_with_installments: CreateAgreementWithInstallments,
    mirante: Condominium,
    jose: Debtor,
    create_user: CreateUser,
    authenticate_as: AuthenticateAs,
) -> None:
    link_client(client_user, mirante)
    create_agreement_with_installments(
        mirante, jose, [(date(2026, 2, 10), date(2026, 2, 12))]
    )
    notifications = ClientNotificationService(
        db_session,
        ClientNotificationRepository(db_session),
        outbox,
        clock,
        settings.frontend_url,
    )
    reports = CondominiumMonthlyReportService(
        db_session,
        CondominiumMonthlyReportRepository(db_session),
        notifications,
        DatabaseStorage(),
        clock,
    )
    reports.close_previous_month()
    headers = authenticate_as(
        create_user(role=Role.CLIENT, email="unlinked@example.com")
    )

    response = db_client.get(
        f"/client-panel/condominiums/{mirante.id}/reports/2026/2",
        headers=headers,
    )

    assert response.status_code == 404
