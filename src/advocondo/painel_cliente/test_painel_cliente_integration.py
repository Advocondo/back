from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from advocondo.acordos.models import Agreement
from advocondo.condominios.models import Condominium
from advocondo.devedores.models import Debtor
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

URL = "/client-panel/agreements"
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
                "debtor_name": "José Simão",
                "debtor_unit": "Bloco B 304",
                "status": "atrasado",
                "overdue_installments": 2,
                "next_due_date": "2026-05-10",
            },
            {
                "id": response.json()[1]["id"],
                "condominium_name": "Edifício Aurora",
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
